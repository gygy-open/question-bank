"""add media_assets and import_tasks.source_sha256

Revision ID: d4e8a1b2c3f5
Revises: c3f1a9e27b54
Create Date: 2026-09-30 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e8a1b2c3f5'
down_revision: Union[str, Sequence[str], None] = 'c3f1a9e27b54'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'media_assets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('subject_id', sa.Integer(), nullable=True),
        sa.Column('owner_user_id', sa.Integer(), nullable=True),
        sa.Column('purpose', sa.String(length=16), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('mime', sa.String(length=100), nullable=False),
        sa.Column('byte_size', sa.BigInteger(), nullable=False),
        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('duration', sa.Float(), nullable=True),
        sa.Column('original_filename', sa.String(length=255), nullable=True),
        sa.Column('alt', sa.String(length=500), nullable=True),
        sa.Column('source', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['owner_user_id'], ['user.id'], name=op.f('fk_media_assets_owner_user_id_user')),
        sa.ForeignKeyConstraint(['subject_id'], ['subjects.id'], name=op.f('fk_media_assets_subject_id_subjects')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_media_assets')),
    )
    with op.batch_alter_table('media_assets', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_media_assets_deleted_at'), ['deleted_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_media_assets_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_media_assets_owner_user_id'), ['owner_user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_media_assets_sha256'), ['sha256'], unique=False)
        batch_op.create_index(batch_op.f('ix_media_assets_subject_id'), ['subject_id'], unique=False)

    with op.batch_alter_table('import_tasks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('source_sha256', sa.String(length=64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('import_tasks', schema=None) as batch_op:
        batch_op.drop_column('source_sha256')

    with op.batch_alter_table('media_assets', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_media_assets_subject_id'))
        batch_op.drop_index(batch_op.f('ix_media_assets_sha256'))
        batch_op.drop_index(batch_op.f('ix_media_assets_owner_user_id'))
        batch_op.drop_index(batch_op.f('ix_media_assets_id'))
        batch_op.drop_index(batch_op.f('ix_media_assets_deleted_at'))
    op.drop_table('media_assets')
