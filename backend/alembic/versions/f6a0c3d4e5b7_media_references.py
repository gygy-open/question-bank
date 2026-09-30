"""add media_references

Revision ID: f6a0c3d4e5b7
Revises: e5f9b2c3d4a6
Create Date: 2026-09-30 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f6a0c3d4e5b7'
down_revision: Union[str, Sequence[str], None] = 'e5f9b2c3d4a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'media_references',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('owner_type', sa.String(length=32), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['media_assets.id'], name=op.f('fk_media_references_asset_id_media_assets')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_media_references')),
        sa.UniqueConstraint('asset_id', 'owner_type', 'owner_id', name='uq_media_references_asset_owner'),
    )
    with op.batch_alter_table('media_references', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_media_references_asset_id'), ['asset_id'], unique=False)
        batch_op.create_index('ix_media_references_owner', ['owner_type', 'owner_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('media_references', schema=None) as batch_op:
        batch_op.drop_index('ix_media_references_owner')
        batch_op.drop_index(batch_op.f('ix_media_references_asset_id'))
    op.drop_table('media_references')
