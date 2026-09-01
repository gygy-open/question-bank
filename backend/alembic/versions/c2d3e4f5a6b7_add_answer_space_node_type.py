"""add answer_space composition node type

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-09-01 00:00:00.000000

Adds ``answer_space`` as an allowed ``block`` node_type on ``composition_nodes``
by widening the ``ck_composition_nodes_kind_matches_type`` CHECK constraint.

Dialect-agnostic (SQLite + MySQL) via batch mode: on SQLite the table is
recreated with the new constraint set; on MySQL 8 the check constraint is
dropped and re-added in place.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c2d3e4f5a6b7'
down_revision: Union[str, Sequence[str], None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Logical name; the metadata naming convention renders it to
# ``ck_composition_nodes_kind_matches_type`` in batch mode.
_KIND_MATCHES_TYPE = 'kind_matches_type'

_NEW_CHECK = (
    "(node_kind = 'block' AND node_type IN "
    "('rich_text', 'heading', 'question', 'page_break', 'answer_space')) OR "
    "(node_kind = 'module' AND node_type = 'question_details') OR "
    "(node_kind = 'reference' AND node_type = 'answer_item')"
)

_OLD_CHECK = (
    "(node_kind = 'block' AND node_type IN "
    "('rich_text', 'heading', 'question', 'page_break')) OR "
    "(node_kind = 'module' AND node_type = 'question_details') OR "
    "(node_kind = 'reference' AND node_type = 'answer_item')"
)


def upgrade() -> None:
    with op.batch_alter_table('composition_nodes', schema=None) as batch_op:
        batch_op.drop_constraint(_KIND_MATCHES_TYPE, type_='check')
        batch_op.create_check_constraint(_KIND_MATCHES_TYPE, _NEW_CHECK)


def downgrade() -> None:
    with op.batch_alter_table('composition_nodes', schema=None) as batch_op:
        batch_op.drop_constraint(_KIND_MATCHES_TYPE, type_='check')
        batch_op.create_check_constraint(_KIND_MATCHES_TYPE, _OLD_CHECK)
