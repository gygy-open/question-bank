"""index question relation targets

Revision ID: a8c4e7f19b2d
Revises: d53ff6ff31fe
Create Date: 2026-09-21 00:00:00.000000

"""
from collections.abc import Sequence
from typing import Union

from alembic import op


revision: str = "a8c4e7f19b2d"
down_revision: Union[str, Sequence[str], None] = "d53ff6ff31fe"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX_NAME = "ix_question_relations_target_question_id_relation_type"


def upgrade() -> None:
    with op.batch_alter_table("question_relations", schema=None) as batch_op:
        batch_op.create_index(
            _INDEX_NAME,
            ["target_question_id", "relation_type"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("question_relations", schema=None) as batch_op:
        batch_op.drop_index(_INDEX_NAME)
