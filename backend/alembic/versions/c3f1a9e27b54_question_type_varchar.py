"""store questions.q_type as varchar (adds option_matching)

Revision ID: c3f1a9e27b54
Revises: 842a88641edd
Create Date: 2026-09-29 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3f1a9e27b54'
down_revision: Union[str, Sequence[str], None] = '842a88641edd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LEGACY_TYPES = (
    'single_choice', 'multiple_choice', 'true_false', 'fill_in_the_blank', 'free_response',
)
_LEGACY_ENUM = sa.Enum(*_LEGACY_TYPES, name='questiontype')


def upgrade() -> None:
    with op.batch_alter_table('questions') as batch_op:
        batch_op.alter_column(
            'q_type',
            existing_type=_LEGACY_ENUM,
            type_=sa.String(length=32),
            existing_nullable=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    newer = bind.execute(
        sa.text('SELECT COUNT(*) FROM questions WHERE q_type NOT IN :types').bindparams(
            sa.bindparam('types', expanding=True)
        ),
        {'types': list(_LEGACY_TYPES)},
    ).scalar()
    if newer:
        raise RuntimeError(
            f'{newer} questions use a q_type unknown to the previous schema '
            '(e.g. option_matching); convert or delete them before downgrading.'
        )
    with op.batch_alter_table('questions') as batch_op:
        batch_op.alter_column(
            'q_type',
            existing_type=sa.String(length=32),
            type_=_LEGACY_ENUM,
            existing_nullable=False,
        )
