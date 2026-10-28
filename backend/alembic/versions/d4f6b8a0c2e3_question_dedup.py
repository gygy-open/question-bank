"""question dedup signatures

Revision ID: d4f6b8a0c2e3
Revises: c3e5a7b9d1f2
Create Date: 2026-10-28 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision: str = 'd4f6b8a0c2e3'
down_revision: Union[str, Sequence[str], None] = 'c3e5a7b9d1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('questions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('dedup_fingerprint', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('dedup_text', mysql.LONGTEXT().with_variant(sa.Text(), 'sqlite'), nullable=True))
        batch_op.add_column(sa.Column('dedup_version', sa.SmallInteger(), nullable=True))
        batch_op.create_index('ix_questions_subject_dedup_fingerprint', ['subject_id', 'dedup_fingerprint'], unique=False)

    op.create_table('question_dedup_bands',
    sa.Column('question_id', sa.Integer(), nullable=False),
    sa.Column('band', sa.SmallInteger(), nullable=False),
    sa.Column('subject_id', sa.Integer(), nullable=True),
    sa.Column('hash', sa.BigInteger(), nullable=False),
    sa.ForeignKeyConstraint(['question_id'], ['questions.id'], name=op.f('fk_question_dedup_bands_question_id_questions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('question_id', 'band', name=op.f('pk_question_dedup_bands'))
    )
    with op.batch_alter_table('question_dedup_bands', schema=None) as batch_op:
        batch_op.create_index('ix_question_dedup_bands_lookup', ['subject_id', 'band', 'hash'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('question_dedup_bands', schema=None) as batch_op:
        batch_op.drop_index('ix_question_dedup_bands_lookup')
    op.drop_table('question_dedup_bands')

    with op.batch_alter_table('questions', schema=None) as batch_op:
        batch_op.drop_index('ix_questions_subject_dedup_fingerprint')
        batch_op.drop_column('dedup_version')
        batch_op.drop_column('dedup_text')
        batch_op.drop_column('dedup_fingerprint')
