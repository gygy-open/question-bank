"""paper import: file hash, idempotency, composition link

Revision ID: b7c1e94d2a35
Revises: d4e5f6a7b8c9
Create Date: 2026-09-17 10:12:44.512038

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c1e94d2a35'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('import_tasks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('content_sha256', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('idempotency_key', sa.String(length=64), nullable=True))
        batch_op.add_column(
            sa.Column(
                'composition_state',
                sa.Enum(
                    'not_requested', 'created', 'failed',
                    name='compositionimportstate',
                ),
                server_default='not_requested',
                nullable=False,
            )
        )
        batch_op.create_index(
            batch_op.f('ix_import_tasks_content_sha256'), ['content_sha256'], unique=False
        )
        batch_op.create_unique_constraint(
            'uq_import_tasks_idempotency_key', ['idempotency_key']
        )

    with op.batch_alter_table('compositions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('source_import_task_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('source_snapshot', sa.JSON(), nullable=True))
        batch_op.create_index(
            batch_op.f('ix_compositions_source_import_task_id'),
            ['source_import_task_id'],
            unique=False,
        )
        batch_op.create_foreign_key(
            op.f('fk_compositions_source_import_task_id_import_tasks'),
            'import_tasks',
            ['source_import_task_id'],
            ['id'],
            ondelete='SET NULL',
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('compositions', schema=None) as batch_op:
        batch_op.drop_constraint(
            op.f('fk_compositions_source_import_task_id_import_tasks'), type_='foreignkey'
        )
        batch_op.drop_index(batch_op.f('ix_compositions_source_import_task_id'))
        batch_op.drop_column('source_snapshot')
        batch_op.drop_column('source_import_task_id')

    with op.batch_alter_table('import_tasks', schema=None) as batch_op:
        batch_op.drop_constraint('uq_import_tasks_idempotency_key', type_='unique')
        batch_op.drop_index(batch_op.f('ix_import_tasks_content_sha256'))
        batch_op.drop_column('composition_state')
        batch_op.drop_column('idempotency_key')
        batch_op.drop_column('content_sha256')
