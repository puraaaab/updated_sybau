"""Initial schema with user status fields

Revision ID: 0001
Revises: 
Create Date: 2026-07-27 14:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Upgrade user table columns if missing
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('status', sa.String(), server_default='active', nullable=False))
        batch_op.add_column(sa.Column('must_change_password', sa.Boolean(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('deleted_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('deleted_at')
        batch_op.drop_column('must_change_password')
        batch_op.drop_column('status')
