"""struct_elements.content_sig for same-condition lookup

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-11-05 11:00:00.000000

条件内容签名(规格 docs/specs/question-structure.md §12.3 N3):按归一化后的条件内容
找共享相同条件的题。存量数据由数据迁移 ``struct_content_sig_v<DEDUP_VERSION>`` 回填。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e3f4a5b6c7d8"
down_revision: Union[str, Sequence[str], None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("struct_elements") as batch_op:
        batch_op.add_column(sa.Column("content_sig", sa.String(length=64), nullable=True))
        batch_op.create_index(batch_op.f("ix_struct_elements_content_sig"), ["content_sig"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("struct_elements") as batch_op:
        batch_op.drop_index(batch_op.f("ix_struct_elements_content_sig"))
        batch_op.drop_column("content_sig")
