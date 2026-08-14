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
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if 'users' not in tables:
        op.create_table(
            'users',
            sa.Column('id', sa.Integer(), primary_key=True, index=True),
            sa.Column('username', sa.String(), unique=True, index=True, nullable=False),
            sa.Column('hashed_password', sa.String(), nullable=False),
            sa.Column('role', sa.String(), server_default='viewer', nullable=False),
            sa.Column('status', sa.String(), server_default='active', nullable=False),
            sa.Column('must_change_password', sa.Boolean(), server_default='0', nullable=False),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=True)
        )
    else:
        columns = [c['name'] for c in inspector.get_columns('users')]
        with op.batch_alter_table('users', schema=None) as batch_op:
            if 'status' not in columns:
                batch_op.add_column(sa.Column('status', sa.String(), server_default='active', nullable=False))
            if 'must_change_password' not in columns:
                batch_op.add_column(sa.Column('must_change_password', sa.Boolean(), server_default='0', nullable=False))
            if 'deleted_at' not in columns:
                batch_op.add_column(sa.Column('deleted_at', sa.DateTime(), nullable=True))



def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('deleted_at')
        batch_op.drop_column('must_change_password')
        batch_op.drop_column('status')
