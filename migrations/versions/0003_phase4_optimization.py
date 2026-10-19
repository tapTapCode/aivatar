"""Phase 4 budget planning, visual strategies, and cross-project asset cache."""
from alembic import op
import sqlalchemy as sa

revision = "0003_phase4_optimization"
down_revision = "0002_scene_layout"
branch_labels = None
depends_on = None


def _columns(bind, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(table)}


def upgrade():
    bind = op.get_bind()
    project_columns = _columns(bind, "projects")
    if "budget_usd" not in project_columns:
        op.add_column("projects", sa.Column("budget_usd", sa.Float(), nullable=False, server_default="5.0"))
    if "visual_density" not in project_columns:
        op.add_column("projects", sa.Column("visual_density", sa.Float(), nullable=False, server_default="0.65"))

    scene_columns = _columns(bind, "scenes")
    if "asset_strategy" not in scene_columns:
        op.add_column("scenes", sa.Column("asset_strategy", sa.String(length=40), nullable=False, server_default="flux_motion"))
    if "motion_score" not in scene_columns:
        op.add_column("scenes", sa.Column("motion_score", sa.Float(), nullable=False, server_default="0"))
    if "estimated_visual_cost_usd" not in scene_columns:
        op.add_column("scenes", sa.Column("estimated_visual_cost_usd", sa.Float(), nullable=False, server_default="0"))
    if "graphic_template" not in scene_columns:
        op.add_column("scenes", sa.Column("graphic_template", sa.String(length=60), nullable=True))

    asset_columns = _columns(bind, "assets")
    if "cache_key" not in asset_columns:
        op.add_column("assets", sa.Column("cache_key", sa.String(length=64), nullable=True))
        op.create_index("ix_assets_cache_key", "assets", ["cache_key"], unique=False)

    if "asset_cache" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "asset_cache",
            sa.Column("cache_key", sa.String(length=64), primary_key=True),
            sa.Column("kind", sa.String(length=40), nullable=False),
            sa.Column("provider", sa.String(length=80), nullable=False),
            sa.Column("model", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("path", sa.Text(), nullable=False),
            sa.Column("checksum", sa.String(length=64), nullable=True),
            sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("hit_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("metadata_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("last_used_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_asset_cache_kind", "asset_cache", ["kind"], unique=False)


def downgrade():
    bind = op.get_bind()
    if "asset_cache" in sa.inspect(bind).get_table_names():
        op.drop_index("ix_asset_cache_kind", table_name="asset_cache")
        op.drop_table("asset_cache")
    if "cache_key" in _columns(bind, "assets"):
        op.drop_index("ix_assets_cache_key", table_name="assets")
        op.drop_column("assets", "cache_key")
    for column in ["graphic_template", "estimated_visual_cost_usd", "motion_score", "asset_strategy"]:
        if column in _columns(bind, "scenes"):
            op.drop_column("scenes", column)
    for column in ["visual_density", "budget_usd"]:
        if column in _columns(bind, "projects"):
            op.drop_column("projects", column)
