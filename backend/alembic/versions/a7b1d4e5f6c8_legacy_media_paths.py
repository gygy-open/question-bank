"""add legacy_media_paths

Revision ID: a7b1d4e5f6c8
Revises: f6a0c3d4e5b7
Create Date: 2026-09-30 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7b1d4e5f6c8'
down_revision: Union[str, Sequence[str], None] = 'f6a0c3d4e5b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'legacy_media_paths',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('old_path', sa.String(length=512), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('mime', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_legacy_media_paths')),
        sa.UniqueConstraint('old_path', name=op.f('uq_legacy_media_paths_old_path')),
    )
    with op.batch_alter_table('legacy_media_paths', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_legacy_media_paths_sha256'), ['sha256'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('legacy_media_paths', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_legacy_media_paths_sha256'))
    op.drop_table('legacy_media_paths')
