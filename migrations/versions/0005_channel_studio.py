"""Persist Channel Studio production options on existing projects."""
from alembic import op
import sqlalchemy as sa
revision = '0005_channel_studio'
down_revision = '0004_phase5_hardening'
branch_labels = None
depends_on = None

def upgrade():
    columns = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('projects')}
    if 'production_json' not in columns:
        op.add_column('projects', sa.Column('production_json',sa.JSON(),server_default='{}',nullable=False))

def downgrade():
    with op.batch_alter_table('projects') as batch:
        batch.drop_column('production_json')

