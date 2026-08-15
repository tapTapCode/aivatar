from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from src.api.durable_repository import DurableControlPlaneRepository
from src.api.repository import ControlPlaneRepository
from src.auth.database import AuthDatabase
from src.orchestration.recovery import job_is_stale, requeue_stranded_job
from src.schemas.jobs import JobRecord, JobState, WatermarkStatus


def _job(job_id: str, *, state: JobState, updated_at: datetime) -> JobRecord:
    job = JobRecord(
        job_id=job_id,
        video_id=f"vid_{job_id}",
        project_id="recovery_script",
        owner_id="owner-recovery",
        idempotency_key=f"idem-{job_id}",
        request_fingerprint=f"fp-{job_id}",
        watermark_status=WatermarkStatus.PRESERVED,
        state=state,
        updated_at=updated_at,
    )
    return job


def test_stale_preprocessing_is_requeued_and_fresh_is_not() -> None:
    now = datetime.now(UTC)
    stale = _job("job_stale", state=JobState.PREPROCESSING, updated_at=now - timedelta(seconds=90))
    fresh = _job("job_fresh", state=JobState.PREPROCESSING, updated_at=now - timedelta(seconds=5))
    assert job_is_stale(stale, now=now, claim_lease_seconds=60, running_lease_seconds=600)
    assert not job_is_stale(fresh, now=now, claim_lease_seconds=60, running_lease_seconds=600)
    requeue_stranded_job(stale)
    assert stale.state == JobState.QUEUED
    assert stale.attempt == 1
    assert stale.transitions[-1].stage == "stale_recovery"


def test_running_job_uses_longer_lease() -> None:
    now = datetime.now(UTC)
    rendering = _job(
        "job_render",
        state=JobState.RENDERING_SCENE,
        updated_at=now - timedelta(seconds=90),
    )
    assert not job_is_stale(
        rendering, now=now, claim_lease_seconds=60, running_lease_seconds=600
    )
    rendering.updated_at = now - timedelta(seconds=601)
    assert job_is_stale(rendering, now=now, claim_lease_seconds=60, running_lease_seconds=600)


def test_memory_repository_requeues_then_claims_stale_job() -> None:
    store = ControlPlaneRepository()

    async def scenario() -> None:
        stale = _job(
            "job_mem_stale",
            state=JobState.PREPROCESSING,
            updated_at=datetime.now(UTC) - timedelta(seconds=120),
        )
        await store.save_job(stale)
        recovered = await store.requeue_stale_jobs(
            claim_lease_seconds=60, running_lease_seconds=600
        )
        assert [job.job_id for job in recovered] == ["job_mem_stale"]
        claimed = await store.claim_next_queued_job()
        assert claimed is not None
        assert claimed.job_id == "job_mem_stale"
        assert claimed.state == JobState.PREPROCESSING

    asyncio.run(scenario())


def test_durable_repository_requeues_stale_preprocessing(tmp_path: Path) -> None:
    database = AuthDatabase(f"sqlite+aiosqlite:///{tmp_path / 'recovery.db'}")
    repository = DurableControlPlaneRepository(database)

    async def scenario() -> None:
        await repository.ensure_schema()
        stale = _job(
            "job_neon_stale",
            state=JobState.PREPROCESSING,
            updated_at=datetime.now(UTC) - timedelta(seconds=180),
        )
        await repository.create_job(stale)
        await repository.save_job(stale)
        recovered = await repository.requeue_stale_jobs(
            claim_lease_seconds=60, running_lease_seconds=600
        )
        assert [job.job_id for job in recovered] == ["job_neon_stale"]
        stored = await repository.get_job("job_neon_stale", owner_id="owner-recovery")
        assert stored is not None
        assert stored.state == JobState.QUEUED
        claimed = await repository.claim_next_queued_job()
        assert claimed is not None
        assert claimed.job_id == "job_neon_stale"
        assert claimed.state == JobState.PREPROCESSING
        assert claimed.transitions[-1].stage == "queue_recovery"

    asyncio.run(scenario())
    asyncio.run(database.dispose())
