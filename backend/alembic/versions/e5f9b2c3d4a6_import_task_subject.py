"""add import_tasks.subject_id

Revision ID: e5f9b2c3d4a6
Revises: d4e8a1b2c3f5
Create Date: 2026-09-30 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f9b2c3d4a6'
down_revision: Union[str, Sequence[str], None] = 'd4e8a1b2c3f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('import_tasks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('subject_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f('fk_import_tasks_subject_id_subjects'), 'subjects', ['subject_id'], ['id']
        )


def downgrade() -> None:
    with op.batch_alter_table('import_tasks', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('fk_import_tasks_subject_id_subjects'), type_='foreignkey')
        batch_op.drop_column('subject_id')
