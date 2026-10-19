from sqlalchemy import create_engine, inspect

from pipeline.models import entities  # noqa: F401
from pipeline.storage.db import Base


def test_phase5_schema_contains_recovery_locks_and_metrics():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    assert "production_runs" in inspector.get_table_names()
    project_columns = {c["name"] for c in inspector.get_columns("projects")}
    job_columns = {c["name"] for c in inspector.get_columns("jobs")}
    assert {"lock_owner", "lock_expires_at"} <= project_columns
    assert {"max_attempts", "retryable", "resume_count", "heartbeat_at", "cancel_requested"} <= job_columns
