from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.auth.models import Base


class ControlPlaneProject(Base):
    __tablename__ = "control_plane_projects"
    __table_args__ = (UniqueConstraint("owner_id", "project_id", name="uq_control_plane_project"),)

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(80), index=True)
    project_id: Mapped[str] = mapped_column(String(80), index=True)
    approval_state: Mapped[str] = mapped_column(String(20), default="draft")
    payload: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ControlPlaneJob(Base):
    __tablename__ = "control_plane_jobs"
    __table_args__ = (
        UniqueConstraint("owner_id", "idempotency_key", name="uq_control_plane_job_idempotency"),
    )

    job_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    video_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    owner_id: Mapped[str] = mapped_column(String(80), index=True)
    project_id: Mapped[str] = mapped_column(String(80), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(200))
    request_fingerprint: Mapped[str] = mapped_column(String(128))
    state: Mapped[str] = mapped_column(String(40), index=True)
    cancellation_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
