from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from src.api.control_plane_models import ControlPlaneJob, ControlPlaneProject
from src.auth.database import AuthDatabase
from src.orchestration.recovery import (
    CLAIMED_STATES,
    RUNNING_STATES,
    job_is_stale,
    requeue_stranded_job,
)
from src.orchestration.state_machine import JobStateMachine
from src.schemas.jobs import JobRecord, JobState
from src.schemas.scene import ProjectScript


def _now() -> datetime:
    return datetime.now(UTC)


def _project_row_id(owner_id: str, project_id: str) -> str:
    return f"{owner_id}:{project_id}"


class DurableControlPlaneRepository:
    """Postgres-backed project and job store used on Neon/Vercel."""

    def __init__(self, database: AuthDatabase) -> None:
        self.database = database

    async def ensure_schema(self) -> None:
        async with self.database.engine.begin() as connection:
            await connection.run_sync(
                lambda sync_connection: ControlPlaneJob.metadata.create_all(
                    sync_connection,
                    tables=[ControlPlaneProject.__table__, ControlPlaneJob.__table__],
                )
            )

    async def put_project(self, project: ProjectScript, *, owner_id: str) -> None:
        await self._upsert_project(project, owner_id=owner_id)

    async def save_draft(self, project: ProjectScript, *, owner_id: str) -> ProjectScript:
        draft = project.model_copy(update={"approval_state": "draft"})
        await self._upsert_project(draft, owner_id=owner_id)
        return draft

    async def approve_project(self, project_id: str, *, owner_id: str) -> ProjectScript | None:
        stored = await self.get_project(project_id, owner_id=owner_id)
        if stored is None:
            return None
        approved = stored.model_copy(update={"approval_state": "approved"})
        await self._upsert_project(approved, owner_id=owner_id)
        return approved

    async def get_project(self, project_id: str, *, owner_id: str) -> ProjectScript | None:
        async with self.database.sessions() as session:
            row = await session.get(ControlPlaneProject, _project_row_id(owner_id, project_id))
            return ProjectScript.model_validate(row.payload) if row else None

    async def delete_project(self, project_id: str, *, owner_id: str) -> bool:
        async with self.database.sessions() as session:
            row = await session.get(
                ControlPlaneProject, _project_row_id(owner_id, project_id)
            )
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    async def list_projects(self, *, owner_id: str) -> list[ProjectScript]:
        async with self.database.sessions() as session:
            rows = (
                await session.scalars(
                    select(ControlPlaneProject)
                    .where(ControlPlaneProject.owner_id == owner_id)
                    .order_by(ControlPlaneProject.project_id)
                )
            ).all()
        return [ProjectScript.model_validate(row.payload) for row in rows]

    async def create_job(self, job: JobRecord) -> tuple[JobRecord, bool]:
        async with self.database.sessions() as session:
            existing = await session.scalar(
                select(ControlPlaneJob).where(
                    ControlPlaneJob.owner_id == job.owner_id,
                    ControlPlaneJob.idempotency_key == job.idempotency_key,
                )
            )
            if existing is not None:
                stored = JobRecord.model_validate(existing.payload)
                if stored.request_fingerprint != job.request_fingerprint:
                    raise ValueError("idempotency key was already used for a different request")
                return stored, False
            session.add(self._job_row(job))
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise ValueError(
                    "idempotency key was already used for a different request"
                ) from exc
        return job, True

    async def save_job(self, job: JobRecord) -> None:
        async with self.database.sessions() as session:
            row = await session.get(ControlPlaneJob, job.job_id)
            if row is None:
                session.add(self._job_row(job))
            else:
                row.video_id = job.video_id
                row.project_id = job.project_id
                row.request_fingerprint = job.request_fingerprint
                row.state = job.state.value
                row.cancellation_requested = job.cancellation_requested
                row.payload = job.model_dump(mode="json")
                row.updated_at = job.updated_at
            await session.commit()

    async def get_job(self, job_id: str, *, owner_id: str) -> JobRecord | None:
        job = await self.get_internal_job(job_id)
        return job if job and job.owner_id == owner_id else None

    async def get_internal_job(self, job_id: str) -> JobRecord | None:
        async with self.database.sessions() as session:
            row = await session.get(ControlPlaneJob, job_id)
            return JobRecord.model_validate(row.payload) if row else None

    async def get_video_job(self, video_id: str, *, owner_id: str) -> JobRecord | None:
        async with self.database.sessions() as session:
            row = await session.scalar(
                select(ControlPlaneJob).where(ControlPlaneJob.video_id == video_id)
            )
            if row is None or row.owner_id != owner_id:
                return None
            return JobRecord.model_validate(row.payload)

    async def list_jobs(self, *, owner_id: str) -> list[JobRecord]:
        async with self.database.sessions() as session:
            rows = (
                await session.scalars(
                    select(ControlPlaneJob)
                    .where(ControlPlaneJob.owner_id == owner_id)
                    .order_by(ControlPlaneJob.created_at.desc())
                )
            ).all()
        return [JobRecord.model_validate(row.payload) for row in rows]

    async def claim_job(self, job_id: str) -> JobRecord | None:
        async with self.database.sessions() as session:
            stmt = select(ControlPlaneJob).where(
                ControlPlaneJob.job_id == job_id,
                ControlPlaneJob.state == JobState.QUEUED.value,
            )
            row = await session.scalar(self._lock_queued_statement(stmt))
            if row is None:
                return None
            job = self._mark_claimed(row, stage="project_setup")
            await session.commit()
            return job

    async def requeue_stale_jobs(
        self,
        *,
        claim_lease_seconds: float,
        running_lease_seconds: float,
        limit: int = 20,
    ) -> list[JobRecord]:
        now = _now()
        claim_cutoff = now - timedelta(seconds=claim_lease_seconds)
        running_cutoff = now - timedelta(seconds=running_lease_seconds)
        recovered: list[JobRecord] = []
        async with self.database.sessions() as session:
            stmt = (
                select(ControlPlaneJob)
                .where(
                    or_(
                        (ControlPlaneJob.state.in_([state.value for state in CLAIMED_STATES]))
                        & (ControlPlaneJob.updated_at <= claim_cutoff),
                        (ControlPlaneJob.state.in_([state.value for state in RUNNING_STATES]))
                        & (ControlPlaneJob.updated_at <= running_cutoff),
                    )
                )
                .order_by(ControlPlaneJob.updated_at)
                .limit(limit)
            )
            rows = (await session.scalars(self._lock_queued_statement(stmt))).all()
            for row in rows:
                job = JobRecord.model_validate(row.payload)
                if not job_is_stale(
                    job,
                    now=now,
                    claim_lease_seconds=claim_lease_seconds,
                    running_lease_seconds=running_lease_seconds,
                ):
                    continue
                requeue_stranded_job(job, stage="stale_recovery")
                row.state = job.state.value
                row.payload = job.model_dump(mode="json")
                row.updated_at = job.updated_at
                recovered.append(job)
            if recovered:
                await session.commit()
        return recovered

    async def claim_next_queued_job(self) -> JobRecord | None:
        async with self.database.sessions() as session:
            stmt = (
                select(ControlPlaneJob)
                .where(ControlPlaneJob.state == JobState.QUEUED.value)
                .order_by(ControlPlaneJob.created_at)
                .limit(1)
            )
            row = await session.scalar(self._lock_queued_statement(stmt))
            if row is None:
                return None
            job = self._mark_claimed(row, stage="queue_recovery")
            await session.commit()
            return job

    def _lock_queued_statement(self, stmt):
        if self.database.engine.dialect.name == "postgresql":
            return stmt.with_for_update(skip_locked=True)
        return stmt.with_for_update()

    def _mark_claimed(self, row: ControlPlaneJob, *, stage: str) -> JobRecord:
        job = JobRecord.model_validate(row.payload)
        JobStateMachine().transition(job, JobState.PREPROCESSING, stage=stage)
        row.state = job.state.value
        row.payload = job.model_dump(mode="json")
        row.updated_at = job.updated_at
        return job

    async def _upsert_project(self, project: ProjectScript, *, owner_id: str) -> None:
        row_id = _project_row_id(owner_id, project.project_id)
        async with self.database.sessions() as session:
            row = await session.get(ControlPlaneProject, row_id)
            payload = project.model_dump(mode="json")
            if row is None:
                session.add(
                    ControlPlaneProject(
                        id=row_id,
                        owner_id=owner_id,
                        project_id=project.project_id,
                        approval_state=project.approval_state,
                        payload=payload,
                        updated_at=_now(),
                    )
                )
            else:
                row.approval_state = project.approval_state
                row.payload = payload
                row.updated_at = _now()
            await session.commit()

    def _job_row(self, job: JobRecord) -> ControlPlaneJob:
        return ControlPlaneJob(
            job_id=job.job_id,
            video_id=job.video_id,
            owner_id=job.owner_id,
            project_id=job.project_id,
            idempotency_key=job.idempotency_key,
            request_fingerprint=job.request_fingerprint,
            state=job.state.value,
            cancellation_requested=job.cancellation_requested,
            payload=job.model_dump(mode="json"),
            created_at=job.created_at,
            updated_at=job.updated_at,
        )
