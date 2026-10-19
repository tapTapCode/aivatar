"""Add per-scene presenter composition settings."""
from alembic import op
import sqlalchemy as sa

revision = "0002_scene_layout"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("scenes")}
    if "layout_json" not in columns:
        op.add_column("scenes", sa.Column("layout_json", sa.JSON(), nullable=True))
        op.execute("UPDATE scenes SET layout_json = '{}' WHERE layout_json IS NULL")


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("scenes")}
    if "layout_json" in columns:
        op.drop_column("scenes", "layout_json")
