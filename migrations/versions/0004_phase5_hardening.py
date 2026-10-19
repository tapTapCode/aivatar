"""Phase 5 restart recovery, operator locks, and production metrics."""
from alembic import op
import sqlalchemy as sa

revision = "0004_phase5_hardening"
down_revision = "0003_phase4_optimization"
branch_labels = None
depends_on = None


def _columns(bind, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(table)}


def upgrade():
    bind = op.get_bind()
    project_columns = _columns(bind, "projects")
    if "lock_owner" not in project_columns:
        op.add_column("projects", sa.Column("lock_owner", sa.String(length=160), nullable=True))
    if "lock_expires_at" not in project_columns:
        op.add_column("projects", sa.Column("lock_expires_at", sa.DateTime(), nullable=True))

    job_columns = _columns(bind, "jobs")
    for name, column in [
        ("max_attempts", sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3")),
        ("retryable", sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.true())),
        ("resume_count", sa.Column("resume_count", sa.Integer(), nullable=False, server_default="0")),
        ("heartbeat_at", sa.Column("heartbeat_at", sa.DateTime(), nullable=True)),
        ("cancel_requested", sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false())),
    ]:
        if name not in job_columns:
            op.add_column("jobs", column)

    if "production_runs" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "production_runs",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("project_id", sa.String(length=36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
            sa.Column("kind", sa.String(length=60), nullable=False),
            sa.Column("state", sa.String(length=40), nullable=False),
            sa.Column("wall_seconds", sa.Float(), nullable=False, server_default="0"),
            sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("estimated_cost_usd", sa.Float(), nullable=False, server_default="0"),
            sa.Column("actual_cost_usd", sa.Float(), nullable=False, server_default="0"),
            sa.Column("cost_per_finished_minute", sa.Float(), nullable=False, server_default="0"),
            sa.Column("storage_bytes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("metadata_json", sa.JSON(), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_production_runs_project_id", "production_runs", ["project_id"], unique=False)
        op.create_index("ix_production_runs_kind", "production_runs", ["kind"], unique=False)
        op.create_index("ix_production_runs_state", "production_runs", ["state"], unique=False)


def downgrade():
    bind = op.get_bind()
    if "production_runs" in sa.inspect(bind).get_table_names():
        for idx in ["ix_production_runs_state", "ix_production_runs_kind", "ix_production_runs_project_id"]:
            op.drop_index(idx, table_name="production_runs")
        op.drop_table("production_runs")
    job_columns = _columns(bind, "jobs")
    for name in ["cancel_requested", "heartbeat_at", "resume_count", "retryable", "max_attempts"]:
        if name in job_columns:
            op.drop_column("jobs", name)
    project_columns = _columns(bind, "projects")
    for name in ["lock_expires_at", "lock_owner"]:
        if name in project_columns:
            op.drop_column("projects", name)
