from __future__ import annotations

import time
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pipeline.models.entities import CostEntry, Job, ProductionRun, Project


@contextmanager
def measure_run(db: Session, project: Project, kind: str, metadata: dict | None = None):
    row = ProductionRun(project_id=project.id, kind=kind, state="RUNNING", started_at=datetime.now(timezone.utc), metadata_json=metadata or {})
    db.add(row); db.commit(); db.refresh(row)
    started = time.monotonic()
    try:
        yield row
        row.state = "COMPLETED"
    except Exception as exc:
        row.state = "FAILED"; row.error = str(exc)
        raise
    finally:
        row.wall_seconds = max(0.0, time.monotonic() - started)
        row.finished_at = datetime.now(timezone.utc)
        row.retry_count = int(db.scalar(select(func.sum(Job.resume_count)).where(Job.project_id == project.id)) or 0)
        row.actual_cost_usd = float(db.scalar(select(func.sum(CostEntry.actual_cost_usd)).where(CostEntry.project_id == project.id)) or 0.0)
        row.estimated_cost_usd = float(db.scalar(select(func.sum(CostEntry.estimated_cost_usd)).where(CostEntry.project_id == project.id)) or 0.0)
        duration_minutes = (project.final_duration or project.expected_duration or 0.0) / 60.0
        row.cost_per_finished_minute = row.actual_cost_usd / duration_minutes if duration_minutes > 0 else 0.0
        db.commit()
