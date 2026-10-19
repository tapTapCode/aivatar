from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from pipeline.models.entities import Project


def acquire_project_lock(db: Session, project: Project, owner: str, ttl_seconds: int = 900) -> dict:
    now = datetime.now(timezone.utc)
    expiry = project.lock_expires_at
    if expiry is not None and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if project.lock_owner and expiry and expiry > now and project.lock_owner != owner:
        raise ValueError(f"Project is currently locked by {project.lock_owner}")
    project.lock_owner = owner
    project.lock_expires_at = now + timedelta(seconds=max(60, ttl_seconds))
    db.commit(); db.refresh(project)
    return {"owner": project.lock_owner, "expires_at": project.lock_expires_at}


def release_project_lock(db: Session, project: Project, owner: str, *, force: bool = False) -> None:
    if project.lock_owner and project.lock_owner != owner and not force:
        raise ValueError("Only the lock owner can release this project lock")
    project.lock_owner = None
    project.lock_expires_at = None
    db.commit(); db.refresh(project)


def assert_project_editable(project: Project, owner: str | None = None) -> None:
    if not project.lock_owner:
        return
    expiry = project.lock_expires_at
    if expiry is not None and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if expiry and expiry <= datetime.now(timezone.utc):
        return
    if owner and project.lock_owner == owner:
        return
    raise ValueError(f"Project is locked by {project.lock_owner}")
