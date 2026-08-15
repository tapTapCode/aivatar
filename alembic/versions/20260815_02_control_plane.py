"""Create durable control-plane project and job tables.

Revision ID: 20260815_02
Revises: 20260814_01
Create Date: 2026-08-15
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260815_02"
down_revision: str | None = "20260814_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "control_plane_projects",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("owner_id", sa.String(80), nullable=False),
        sa.Column("project_id", sa.String(80), nullable=False),
        sa.Column("approval_state", sa.String(20), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_id", "project_id", name="uq_control_plane_project"),
    )
    op.create_index("ix_control_plane_projects_owner_id", "control_plane_projects", ["owner_id"])
    op.create_index(
        "ix_control_plane_projects_project_id", "control_plane_projects", ["project_id"]
    )
    op.create_table(
        "control_plane_jobs",
        sa.Column("job_id", sa.String(80), primary_key=True),
        sa.Column("video_id", sa.String(80), nullable=False),
        sa.Column("owner_id", sa.String(80), nullable=False),
        sa.Column("project_id", sa.String(80), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("request_fingerprint", sa.String(128), nullable=False),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("cancellation_requested", sa.Boolean(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_id", "idempotency_key", name="uq_control_plane_job_idempotency"),
    )
    op.create_index(
        "ix_control_plane_jobs_video_id", "control_plane_jobs", ["video_id"], unique=True
    )
    op.create_index("ix_control_plane_jobs_owner_id", "control_plane_jobs", ["owner_id"])
    op.create_index("ix_control_plane_jobs_project_id", "control_plane_jobs", ["project_id"])
    op.create_index("ix_control_plane_jobs_state", "control_plane_jobs", ["state"])


def downgrade() -> None:
    op.drop_table("control_plane_jobs")
    op.drop_table("control_plane_projects")
