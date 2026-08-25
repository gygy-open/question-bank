"""add composition domain tables

Revision ID: 609eb478d6e0
Revises: a7b8c9d0e1f2
Create Date: 2026-08-25 22:13:11.715463

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '609eb478d6e0'
down_revision: Union[str, Sequence[str], None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('folders',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('scope_type', sa.Enum('shared', 'personal', name='scopetype'), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=True),
    sa.Column('subject_id', sa.Integer(), nullable=False),
    sa.Column('parent_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(), nullable=True),
    sa.CheckConstraint("(scope_type = 'shared' AND owner_id IS NULL) OR (scope_type = 'personal' AND owner_id IS NOT NULL)", name=op.f('ck_folders_scope_owner')),
    sa.ForeignKeyConstraint(['created_by'], ['user.id'], name=op.f('fk_folders_created_by_user')),
    sa.ForeignKeyConstraint(['owner_id'], ['user.id'], name=op.f('fk_folders_owner_id_user')),
    sa.ForeignKeyConstraint(['parent_id'], ['folders.id'], name=op.f('fk_folders_parent_id_folders')),
    sa.ForeignKeyConstraint(['subject_id'], ['subjects.id'], name=op.f('fk_folders_subject_id_subjects')),
    sa.ForeignKeyConstraint(['updated_by'], ['user.id'], name=op.f('fk_folders_updated_by_user')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_folders'))
    )
    with op.batch_alter_table('folders', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_folders_deleted_at'), ['deleted_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_folders_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_folders_owner_id'), ['owner_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_folders_parent_id'), ['parent_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_folders_subject_id'), ['subject_id'], unique=False)
        batch_op.create_index('ix_folders_subject_scope_owner', ['subject_id', 'scope_type', 'owner_id'], unique=False)

    op.create_table('compositions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('scope_type', sa.Enum('shared', 'personal', name='scopetype'), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=True),
    sa.Column('subject_id', sa.Integer(), nullable=False),
    sa.Column('folder_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.Column('deleted_at', sa.DateTime(), nullable=True),
    sa.CheckConstraint("(scope_type = 'shared' AND owner_id IS NULL) OR (scope_type = 'personal' AND owner_id IS NOT NULL)", name=op.f('ck_compositions_scope_owner')),
    sa.ForeignKeyConstraint(['created_by'], ['user.id'], name=op.f('fk_compositions_created_by_user')),
    sa.ForeignKeyConstraint(['folder_id'], ['folders.id'], name=op.f('fk_compositions_folder_id_folders')),
    sa.ForeignKeyConstraint(['owner_id'], ['user.id'], name=op.f('fk_compositions_owner_id_user')),
    sa.ForeignKeyConstraint(['subject_id'], ['subjects.id'], name=op.f('fk_compositions_subject_id_subjects')),
    sa.ForeignKeyConstraint(['updated_by'], ['user.id'], name=op.f('fk_compositions_updated_by_user')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_compositions'))
    )
    with op.batch_alter_table('compositions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_compositions_deleted_at'), ['deleted_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_compositions_folder_id'), ['folder_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_compositions_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_compositions_owner_id'), ['owner_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_compositions_subject_id'), ['subject_id'], unique=False)
        batch_op.create_index('ix_compositions_subject_scope_owner', ['subject_id', 'scope_type', 'owner_id'], unique=False)

    op.create_table('composition_blocks',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('composition_id', sa.Integer(), nullable=False),
    sa.Column('sequence', sa.Integer(), nullable=False),
    sa.Column('block_type', sa.Enum('rich_text', 'heading', 'question', 'page_break', 'answer_summary', name='compositionblocktype'), nullable=False),
    sa.Column('content', sa.JSON(), nullable=True),
    sa.Column('props', sa.JSON(), nullable=True),
    sa.Column('schema_version', sa.Integer(), nullable=False),
    sa.Column('question_id', sa.Integer(), nullable=True),
    sa.Column('question_revision', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.CheckConstraint("(block_type = 'question' AND question_id IS NOT NULL AND question_revision IS NOT NULL) OR (block_type <> 'question' AND question_id IS NULL AND question_revision IS NULL)", name=op.f('ck_composition_blocks_question_ref_matches_type')),
    sa.ForeignKeyConstraint(['composition_id'], ['compositions.id'], name=op.f('fk_composition_blocks_composition_id_compositions'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by'], ['user.id'], name=op.f('fk_composition_blocks_created_by_user')),
    sa.ForeignKeyConstraint(['question_id'], ['questions.id'], name=op.f('fk_composition_blocks_question_id_questions')),
    sa.ForeignKeyConstraint(['updated_by'], ['user.id'], name=op.f('fk_composition_blocks_updated_by_user')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_composition_blocks'))
    )
    with op.batch_alter_table('composition_blocks', schema=None) as batch_op:
        batch_op.create_index('ix_composition_blocks_comp_seq', ['composition_id', 'sequence'], unique=False)
        batch_op.create_index(batch_op.f('ix_composition_blocks_composition_id'), ['composition_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_composition_blocks_question_id'), ['question_id'], unique=False)

    op.create_table('composition_events',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
    sa.Column('composition_id', sa.Integer(), nullable=False),
    sa.Column('composition_revision', sa.Integer(), nullable=False),
    sa.Column('event_type', sa.String(length=50), nullable=False),
    sa.Column('target_type', sa.String(length=50), nullable=True),
    sa.Column('target_id', sa.String(length=64), nullable=True),
    sa.Column('summary', sa.String(length=255), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=True),
    sa.Column('batch_id', sa.String(length=64), nullable=True),
    sa.Column('actor_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['actor_id'], ['user.id'], name=op.f('fk_composition_events_actor_id_user')),
    sa.ForeignKeyConstraint(['composition_id'], ['compositions.id'], name=op.f('fk_composition_events_composition_id_compositions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_composition_events'))
    )
    with op.batch_alter_table('composition_events', schema=None) as batch_op:
        batch_op.create_index('ix_composition_events_actor_created', ['actor_id', 'created_at'], unique=False)
        batch_op.create_index('ix_composition_events_comp_id', ['composition_id', 'id'], unique=False)
        batch_op.create_index(batch_op.f('ix_composition_events_composition_id'), ['composition_id'], unique=False)

    op.create_table('composition_versions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('composition_id', sa.Integer(), nullable=False),
    sa.Column('version_no', sa.Integer(), nullable=False),
    sa.Column('source_revision', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('subject_id', sa.Integer(), nullable=False),
    sa.Column('snapshot', sa.JSON(), nullable=False),
    sa.Column('label', sa.String(length=255), nullable=True),
    sa.Column('finalized_at', sa.DateTime(), nullable=False),
    sa.Column('finalized_by', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['composition_id'], ['compositions.id'], name=op.f('fk_composition_versions_composition_id_compositions'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['finalized_by'], ['user.id'], name=op.f('fk_composition_versions_finalized_by_user')),
    sa.ForeignKeyConstraint(['subject_id'], ['subjects.id'], name=op.f('fk_composition_versions_subject_id_subjects')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_composition_versions')),
    sa.UniqueConstraint('composition_id', 'version_no', name='composition_version_no')
    )
    with op.batch_alter_table('composition_versions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_composition_versions_composition_id'), ['composition_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_composition_versions_id'), ['id'], unique=False)

    with op.batch_alter_table('questions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('content_revision', sa.Integer(), server_default='1', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('questions', schema=None) as batch_op:
        batch_op.drop_column('content_revision')

    with op.batch_alter_table('composition_versions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_composition_versions_id'))
        batch_op.drop_index(batch_op.f('ix_composition_versions_composition_id'))

    op.drop_table('composition_versions')
    with op.batch_alter_table('composition_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_composition_events_composition_id'))
        batch_op.drop_index('ix_composition_events_comp_id')
        batch_op.drop_index('ix_composition_events_actor_created')

    op.drop_table('composition_events')
    with op.batch_alter_table('composition_blocks', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_composition_blocks_question_id'))
        batch_op.drop_index(batch_op.f('ix_composition_blocks_composition_id'))
        batch_op.drop_index('ix_composition_blocks_comp_seq')

    op.drop_table('composition_blocks')
    with op.batch_alter_table('compositions', schema=None) as batch_op:
        batch_op.drop_index('ix_compositions_subject_scope_owner')
        batch_op.drop_index(batch_op.f('ix_compositions_subject_id'))
        batch_op.drop_index(batch_op.f('ix_compositions_owner_id'))
        batch_op.drop_index(batch_op.f('ix_compositions_id'))
        batch_op.drop_index(batch_op.f('ix_compositions_folder_id'))
        batch_op.drop_index(batch_op.f('ix_compositions_deleted_at'))

    op.drop_table('compositions')
    with op.batch_alter_table('folders', schema=None) as batch_op:
        batch_op.drop_index('ix_folders_subject_scope_owner')
        batch_op.drop_index(batch_op.f('ix_folders_subject_id'))
        batch_op.drop_index(batch_op.f('ix_folders_parent_id'))
        batch_op.drop_index(batch_op.f('ix_folders_owner_id'))
        batch_op.drop_index(batch_op.f('ix_folders_id'))
        batch_op.drop_index(batch_op.f('ix_folders_deleted_at'))

    op.drop_table('folders')
