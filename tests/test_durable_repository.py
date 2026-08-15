from __future__ import annotations

import asyncio
from pathlib import Path

from src.api.control_plane_models import ControlPlaneJob, ControlPlaneProject
from src.api.durable_repository import DurableControlPlaneRepository
from src.auth.database import AuthDatabase
from src.schemas.jobs import JobRecord, JobState, WatermarkStatus
from src.schemas.scene import OutputSpec, ProjectScript, Scene

_ = (ControlPlaneProject, ControlPlaneJob)


def _project(project_id: str, narration: str = "Durable script.") -> ProjectScript:
    return ProjectScript(
        project_id=project_id,
        schema_version="1.0",
        output=OutputSpec(width=640, height=360),
        scenes=(
            Scene(
                scene_id="presenter",
                order=1,
                visual_format="PRESENTER",
                narration_text=narration,
                avatar_id="avatar",
                voice_id="voice",
            ),
        ),
    )


def _job(project_id: str, owner_id: str, key: str = "idem-1") -> JobRecord:
    return JobRecord(
        job_id="job_durable",
        video_id="vid_durable",
        project_id=project_id,
        owner_id=owner_id,
        idempotency_key=key,
        request_fingerprint="fp-1",
        watermark_status=WatermarkStatus.PRESERVED,
    )


def test_durable_repository_persists_projects_jobs_and_idempotency(tmp_path: Path) -> None:
    database = AuthDatabase(f"sqlite+aiosqlite:///{tmp_path / 'control.db'}")
    asyncio.run(database.create_schema())
    repository = DurableControlPlaneRepository(database)
    owner = "owner-1"
    project = _project("demo_script")

    async def scenario() -> None:
        draft = await repository.save_draft(project, owner_id=owner)
        assert draft.approval_state == "draft"
        approved = await repository.approve_project("demo_script", owner_id=owner)
        assert approved is not None
        assert approved.approval_state == "approved"
        listed = await repository.list_projects(owner_id=owner)
        assert listed[0].approval_state == "approved"

        created, is_new = await repository.create_job(_job("demo_script", owner))
        assert is_new is True
        created.state = JobState.QUEUED
        await repository.save_job(created)
        stored = await repository.get_job("job_durable", owner_id=owner)
        assert stored is not None
        assert stored.state == JobState.QUEUED
        replay, is_new = await repository.create_job(_job("demo_script", owner))
        assert is_new is False
        assert replay.job_id == created.job_id
        hidden = await repository.get_job("job_durable", owner_id="other")
        assert hidden is None
        by_video = await repository.get_video_job("vid_durable", owner_id=owner)
        assert by_video is not None
        jobs = await repository.list_jobs(owner_id=owner)
        assert [item.job_id for item in jobs] == ["job_durable"]
        assert await repository.delete_project("demo_script", owner_id=owner) is True
        assert await repository.get_project("demo_script", owner_id=owner) is None
        assert await repository.delete_project("demo_script", owner_id=owner) is False

    asyncio.run(scenario())
    asyncio.run(database.dispose())


def test_durable_repository_claims_queued_jobs_in_created_order(tmp_path: Path) -> None:
    database = AuthDatabase(f"sqlite+aiosqlite:///{tmp_path / 'control.db'}")
    asyncio.run(database.create_schema())
    repository = DurableControlPlaneRepository(database)

    async def scenario() -> None:
        first = _job("demo_script", "owner-1", key="idem-1")
        first.job_id = "job_first"
        first.video_id = "vid_first"
        first.state = JobState.QUEUED
        second = _job("demo_script", "owner-1", key="idem-2")
        second.job_id = "job_second"
        second.video_id = "vid_second"
        second.state = JobState.QUEUED
        await repository.create_job(first)
        await repository.save_job(first)
        await repository.create_job(second)
        await repository.save_job(second)

        claimed = await repository.claim_next_queued_job()
        assert claimed is not None
        assert claimed.job_id == "job_first"
        assert claimed.state == JobState.PREPROCESSING
        assert claimed.transitions[-1].stage == "queue_recovery"

        skipped = await repository.claim_job("job_first")
        assert skipped is None

        next_claimed = await repository.claim_job("job_second")
        assert next_claimed is not None
        assert next_claimed.job_id == "job_second"
        assert next_claimed.state == JobState.PREPROCESSING
        assert await repository.claim_next_queued_job() is None

    asyncio.run(scenario())
    asyncio.run(database.dispose())
