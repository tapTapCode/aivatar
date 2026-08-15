from __future__ import annotations

import asyncio

from datetime import UTC, datetime

from src.orchestration.recovery import job_is_stale, requeue_stranded_job
from src.orchestration.state_machine import JobStateMachine
from src.schemas.jobs import JobRecord, JobState
from src.schemas.scene import ProjectScript


class ControlPlaneRepository:
    """Development repository; production deployments replace this with PostgreSQL."""

    def __init__(self) -> None:
        self.projects: dict[tuple[str, str], ProjectScript] = {}
        self.jobs: dict[str, JobRecord] = {}
        self.video_to_job: dict[str, str] = {}
        self.idempotency: dict[tuple[str, str], str] = {}
        self._lock = asyncio.Lock()

    async def put_project(self, project: ProjectScript, *, owner_id: str) -> None:
        async with self._lock:
            self.projects[(owner_id, project.project_id)] = project

    async def save_draft(self, project: ProjectScript, *, owner_id: str) -> ProjectScript:
        draft = project.model_copy(update={"approval_state": "draft"})
        await self.put_project(draft, owner_id=owner_id)
        return draft

    async def approve_project(self, project_id: str, *, owner_id: str) -> ProjectScript | None:
        async with self._lock:
            stored = self.projects.get((owner_id, project_id))
            if stored is None:
                return None
            approved = stored.model_copy(update={"approval_state": "approved"})
            self.projects[(owner_id, project_id)] = approved
            return approved

    async def get_project(self, project_id: str, *, owner_id: str) -> ProjectScript | None:
        async with self._lock:
            return self.projects.get((owner_id, project_id))

    async def save_job(self, job: JobRecord) -> None:
        async with self._lock:
            self.jobs[job.job_id] = job
            self.video_to_job[job.video_id] = job.job_id

    async def get_internal_job(self, job_id: str) -> JobRecord | None:
        async with self._lock:
            return self.jobs.get(job_id)

    async def create_job(self, job: JobRecord) -> tuple[JobRecord, bool]:
        async with self._lock:
            idempotency_key = (job.owner_id, job.idempotency_key)
            existing_id = self.idempotency.get(idempotency_key)
            if existing_id:
                existing = self.jobs[existing_id]
                if existing.request_fingerprint != job.request_fingerprint:
                    raise ValueError("idempotency key was already used for a different request")
                return existing, False
            self.jobs[job.job_id] = job
            self.video_to_job[job.video_id] = job.job_id
            self.idempotency[idempotency_key] = job.job_id
            return job, True

    async def get_job(self, job_id: str, *, owner_id: str) -> JobRecord | None:
        async with self._lock:
            job = self.jobs.get(job_id)
            return job if job and job.owner_id == owner_id else None

    async def get_video_job(self, video_id: str, *, owner_id: str) -> JobRecord | None:
        async with self._lock:
            job_id = self.video_to_job.get(video_id)
            job = self.jobs.get(job_id) if job_id else None
            return job if job and job.owner_id == owner_id else None

    async def delete_project(self, project_id: str, *, owner_id: str) -> bool:
        async with self._lock:
            return self.projects.pop((owner_id, project_id), None) is not None

    async def list_projects(self, *, owner_id: str) -> list[ProjectScript]:
        async with self._lock:
            projects = [project for (oid, _), project in self.projects.items() if oid == owner_id]
            return sorted(projects, key=lambda project: project.project_id)

    async def list_jobs(self, *, owner_id: str) -> list[JobRecord]:
        async with self._lock:
            jobs = [job for job in self.jobs.values() if job.owner_id == owner_id]
            return sorted(jobs, key=lambda job: job.created_at, reverse=True)

    async def claim_job(self, job_id: str) -> JobRecord | None:
        async with self._lock:
            job = self.jobs.get(job_id)
            if job is None or job.state != JobState.QUEUED:
                return None
            JobStateMachine().transition(job, JobState.PREPROCESSING, stage="project_setup")
            return job

    async def requeue_stale_jobs(
        self,
        *,
        claim_lease_seconds: float,
        running_lease_seconds: float,
        limit: int = 20,
    ) -> list[JobRecord]:
        async with self._lock:
            now = datetime.now(UTC)
            stale = [
                job
                for job in self.jobs.values()
                if job_is_stale(
                    job,
                    now=now,
                    claim_lease_seconds=claim_lease_seconds,
                    running_lease_seconds=running_lease_seconds,
                )
            ]
            stale.sort(key=lambda job: job.updated_at)
            recovered: list[JobRecord] = []
            for job in stale[:limit]:
                requeue_stranded_job(job, stage="stale_recovery")
                recovered.append(job)
            return recovered

    async def claim_next_queued_job(self) -> JobRecord | None:
        async with self._lock:
            queued = [job for job in self.jobs.values() if job.state == JobState.QUEUED]
            queued.sort(key=lambda job: job.created_at)
            if not queued:
                return None
            job = queued[0]
            JobStateMachine().transition(job, JobState.PREPROCESSING, stage="queue_recovery")
            return job
