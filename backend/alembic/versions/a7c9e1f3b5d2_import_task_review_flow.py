"""import task review flow

Revision ID: a7c9e1f3b5d2
Revises: d4f6b8a0c2e3
Create Date: 2026-11-01 12:00:00.000000

All imports become background tasks that stop at ``review_ready`` (or ``paused`` when the
AI service is unavailable). Widens the status enum and adds the method / auto_commit /
result / progress / pause columns.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7c9e1f3b5d2'
down_revision: Union[str, Sequence[str], None] = 'd4f6b8a0c2e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_STATUSES = ('pending', 'processing', 'completed', 'failed', 'cancelled')
_NEW_STATUSES = ('pending', 'processing', 'review_ready', 'paused', 'completed', 'failed', 'cancelled')


def upgrade() -> None:
    with op.batch_alter_table('import_tasks', schema=None) as batch_op:
        batch_op.alter_column(
            'status',
            existing_type=sa.Enum(*_OLD_STATUSES, name='importtaskstatus'),
            type_=sa.Enum(*_NEW_STATUSES, name='importtaskstatus'),
            existing_nullable=True,
        )
        batch_op.add_column(sa.Column('method', sa.String(length=20), nullable=True))
        batch_op.add_column(
            sa.Column('auto_commit', sa.Boolean(), server_default=sa.false(), nullable=False)
        )
        batch_op.add_column(sa.Column('result_sha256', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('progress', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('paused_reason', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('provider_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_import_tasks_provider_id'), ['provider_id'], unique=False)

    # 旧的后台批量导入任务一直是"识别后直接入库"。
    op.execute("UPDATE import_tasks SET auto_commit = 1 WHERE source = 'batch_upload'")


def downgrade() -> None:
    op.execute(
        "UPDATE import_tasks SET status = 'pending' WHERE status IN ('review_ready', 'paused')"
    )
    with op.batch_alter_table('import_tasks', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_import_tasks_provider_id'))
        batch_op.drop_column('provider_id')
        batch_op.drop_column('paused_reason')
        batch_op.drop_column('progress')
        batch_op.drop_column('result_sha256')
        batch_op.drop_column('auto_commit')
        batch_op.drop_column('method')
        batch_op.alter_column(
            'status',
            existing_type=sa.Enum(*_NEW_STATUSES, name='importtaskstatus'),
            type_=sa.Enum(*_OLD_STATUSES, name='importtaskstatus'),
            existing_nullable=True,
        )
