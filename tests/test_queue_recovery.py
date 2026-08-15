from __future__ import annotations

import asyncio

from src.api.main import consume_one_job, queue, repository
from src.api.repository import ControlPlaneRepository
from src.queue.memory import InMemoryJobQueue
from src.schemas.jobs import JobRecord, JobState, WatermarkStatus


def _queued_job(job_id: str, owner_id: str = "owner-recovery") -> JobRecord:
    job = JobRecord(
        job_id=job_id,
        video_id=f"vid_{job_id}",
        project_id="recovery_script",
        owner_id=owner_id,
        idempotency_key=f"idem-{job_id}",
        request_fingerprint=f"fp-{job_id}",
        watermark_status=WatermarkStatus.PRESERVED,
    )
    job.state = JobState.QUEUED
    return job


def test_memory_repository_claims_oldest_queued_job() -> None:
    store = ControlPlaneRepository()

    async def scenario() -> None:
        first = _queued_job("job_old")
        second = _queued_job("job_new")
        await store.save_job(first)
        await store.save_job(second)
        claimed = await store.claim_next_queued_job()
        assert claimed is not None
        assert claimed.job_id == "job_old"
        assert claimed.state == JobState.PREPROCESSING
        assert await store.claim_job("job_old") is None
        specific = await store.claim_job("job_new")
        assert specific is not None
        assert specific.job_id == "job_new"

    asyncio.run(scenario())


def test_consume_recovers_orphaned_queued_job(monkeypatch) -> None:
    executed: list[tuple[str, str, bool]] = []

    async def fake_execute(
        job_id: str, owner_id: str, *, already_claimed: bool = False
    ) -> None:
        executed.append((job_id, owner_id, already_claimed))

    monkeypatch.setattr("src.api.main.execute_video_job", fake_execute)
    monkeypatch.setattr("src.api.main.modal_dispatcher", None)

    job = _queued_job("job_orphan")

    async def scenario() -> None:
        while await queue.try_dequeue() is not None:
            pass
        await repository.save_job(job)
        await consume_one_job()

    asyncio.run(scenario())
    assert executed == [("job_orphan", "owner-recovery", True)]
    stored = asyncio.run(repository.get_job("job_orphan", owner_id="owner-recovery"))
    assert stored is not None
    assert stored.state == JobState.PREPROCESSING


def test_consume_requeues_stale_preprocessing_then_runs(monkeypatch) -> None:
    from datetime import UTC, datetime, timedelta

    executed: list[tuple[str, str, bool]] = []

    async def fake_execute(
        job_id: str, owner_id: str, *, already_claimed: bool = False
    ) -> None:
        executed.append((job_id, owner_id, already_claimed))

    monkeypatch.setattr("src.api.main.execute_video_job", fake_execute)
    monkeypatch.setattr("src.api.main.modal_dispatcher", None)
    monkeypatch.setattr("src.api.main.settings.job_claim_lease_seconds", 60)
    monkeypatch.setattr("src.api.main.settings.job_running_lease_seconds", 600)

    job = _queued_job("job_stale_claim")
    job.state = JobState.PREPROCESSING
    job.updated_at = datetime.now(UTC) - timedelta(seconds=180)

    async def scenario() -> None:
        while await queue.try_dequeue() is not None:
            pass
        await repository.save_job(job)
        await consume_one_job()

    asyncio.run(scenario())
    assert executed == [("job_stale_claim", "owner-recovery", True)]
    stored = asyncio.run(repository.get_job("job_stale_claim", owner_id="owner-recovery"))
    assert stored is not None
    assert stored.state == JobState.PREPROCESSING
    assert any(item.stage == "stale_recovery" for item in stored.transitions)


def test_try_dequeue_does_not_block() -> None:
    local_queue = InMemoryJobQueue()

    async def scenario() -> None:
        assert await local_queue.try_dequeue() is None
        from src.queue.base import JobMessage

        message = JobMessage(
            job_id="job_mem",
            video_id="vid_mem",
            project_id="proj",
            owner_id="owner",
        )
        await local_queue.enqueue(message)
        assert await local_queue.try_dequeue() == message
        assert await local_queue.try_dequeue() is None

    asyncio.run(scenario())
