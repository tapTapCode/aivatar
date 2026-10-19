from datetime import datetime, timezone

from pipeline.core.enums import JobState
from pipeline.models.entities import Job
from pipeline.queue.manager import JobManager
from pipeline.storage.db import SessionLocal
from pipeline.storage.migrate import migrate


def test_recovery_marks_exhausted_job_failed():
    migrate()
    manager = JobManager()
    with SessionLocal() as db:
        job = Job(kind="unknown-test", state=JobState.RUNNING.value, attempts=3, max_attempts=3, retryable=True, started_at=datetime.now(timezone.utc))
        db.add(job); db.commit(); db.refresh(job); job_id = job.id
    result = manager.recover_interrupted()
    with SessionLocal() as db:
        recovered = db.get(Job, job_id)
        assert recovered.state == JobState.FAILED.value
    assert result["failed"] >= 1
