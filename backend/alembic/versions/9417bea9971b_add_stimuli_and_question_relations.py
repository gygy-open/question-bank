"""add stimuli, question stimulus link and question relations

Revision ID: 9417bea9971b
Revises: e5f6a7b8c9d0
Create Date: 2026-09-19 21:19:50.988693

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '9417bea9971b'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RICH_TEXT = mysql.LONGTEXT().with_variant(sa.Text(), 'sqlite')


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('stimuli',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('subject_id', sa.Integer(), nullable=False),
    sa.Column('content', _RICH_TEXT, nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('visibility', sa.String(length=20), nullable=False),
    sa.Column('source', sa.String(length=255), nullable=True),
    sa.Column('metadata', _RICH_TEXT, nullable=True),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('content_revision', sa.Integer(), server_default='1', nullable=False),
    sa.Column('deleted_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['user.id'], name=op.f('fk_stimuli_created_by_user')),
    sa.ForeignKeyConstraint(['subject_id'], ['subjects.id'], name=op.f('fk_stimuli_subject_id_subjects')),
    sa.ForeignKeyConstraint(['updated_by'], ['user.id'], name=op.f('fk_stimuli_updated_by_user')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_stimuli'))
    )
    with op.batch_alter_table('stimuli', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_stimuli_deleted_at'), ['deleted_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_stimuli_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_stimuli_subject_id'), ['subject_id'], unique=False)

    with op.batch_alter_table('questions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('stimulus_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('stimulus_position', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_questions_stimulus_id'), ['stimulus_id'], unique=False)
        batch_op.create_unique_constraint(
            'uq_questions_stimulus_position', ['stimulus_id', 'stimulus_position']
        )
        batch_op.create_check_constraint(
            'stimulus_position_non_negative', 'stimulus_position IS NULL OR stimulus_position >= 0'
        )
        batch_op.create_foreign_key(
            batch_op.f('fk_questions_stimulus_id_stimuli'), 'stimuli', ['stimulus_id'], ['id']
        )

    op.create_table('question_relations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source_question_id', sa.Integer(), nullable=False),
    sa.Column('target_question_id', sa.Integer(), nullable=False),
    sa.Column('relation_type', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.CheckConstraint('source_question_id <> target_question_id', name=op.f('ck_question_relations_different_questions')),
    sa.ForeignKeyConstraint(['created_by'], ['user.id'], name=op.f('fk_question_relations_created_by_user')),
    sa.ForeignKeyConstraint(['source_question_id'], ['questions.id'], name=op.f('fk_question_relations_source_question_id_questions')),
    sa.ForeignKeyConstraint(['target_question_id'], ['questions.id'], name=op.f('fk_question_relations_target_question_id_questions')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_question_relations')),
    sa.UniqueConstraint('source_question_id', 'target_question_id', 'relation_type', name='uq_question_relations_edge')
    )
    with op.batch_alter_table('question_relations', schema=None) as batch_op:
        batch_op.create_index(
            'ix_question_relations_target_question_id_relation_type',
            ['target_question_id', 'relation_type'],
            unique=False,
        )
    # Legacy parent_id points child -> parent. The relation graph points source
    # (original parent) -> target (decomposed child); no stimuli are inferred.
    op.execute(
        sa.text(
            """
            INSERT INTO question_relations
                (source_question_id, target_question_id, relation_type, created_at, created_by)
            SELECT parent_id, id, 'decomposed_from', CURRENT_TIMESTAMP, created_by
            FROM questions AS child
            WHERE parent_id IS NOT NULL
              AND parent_id <> id
              AND EXISTS (
                  SELECT 1
                  FROM questions AS parent
                  WHERE parent.id = child.parent_id
                    AND (
                        parent.subject_id = child.subject_id
                        OR (parent.subject_id IS NULL AND child.subject_id IS NULL)
                    )
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM question_relations AS relation
                  WHERE relation.source_question_id = child.parent_id
                    AND relation.target_question_id = child.id
                    AND relation.relation_type = 'decomposed_from'
              )
            """
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    # Dropping the table removes its FK-backing indexes together (MySQL 1553).
    if inspector.has_table("question_relations"):
        op.drop_table("question_relations")

    question_columns = {column["name"] for column in inspector.get_columns("questions")}
    if "stimulus_id" in question_columns:
        # MySQL needs the FK gone before its backing indexes; SQLite batch needs
        # indexes gone before the column. Only FK -> index -> column satisfies both.
        with op.batch_alter_table('questions', schema=None) as batch_op:
            batch_op.drop_constraint(batch_op.f('fk_questions_stimulus_id_stimuli'), type_='foreignkey')
            batch_op.drop_constraint('stimulus_position_non_negative', type_='check')
            batch_op.drop_constraint('uq_questions_stimulus_position', type_='unique')
            batch_op.drop_index(batch_op.f('ix_questions_stimulus_id'))
            batch_op.drop_column('stimulus_position')
            batch_op.drop_column('stimulus_id')

    if inspector.has_table("stimuli"):
        op.drop_table("stimuli")
