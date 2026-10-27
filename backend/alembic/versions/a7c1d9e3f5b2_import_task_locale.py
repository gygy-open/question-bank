"""add import_tasks.locale

Revision ID: a7c1d9e3f5b2
Revises: f45904e15124
Create Date: 2026-10-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7c1d9e3f5b2'
down_revision: Union[str, Sequence[str], None] = 'f45904e15124'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('import_tasks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('locale', sa.String(length=16), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('import_tasks', schema=None) as batch_op:
        batch_op.drop_column('locale')
