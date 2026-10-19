"""Initial Aivatar schema.

The runtime bootstrap also calls metadata.create_all() so mock-mode development is not blocked by Alembic CLI availability.
"""
from alembic import op
from pipeline.storage.db import Base
from pipeline.models import entities  # noqa: F401
revision="0001_initial"; down_revision=None; branch_labels=None; depends_on=None

def upgrade():
    bind=op.get_bind(); Base.metadata.create_all(bind=bind)

def downgrade():
    bind=op.get_bind(); Base.metadata.drop_all(bind=bind)
