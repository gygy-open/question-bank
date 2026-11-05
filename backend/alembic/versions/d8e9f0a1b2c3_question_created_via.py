"""questions.created_via: mark questions created by external agents through MCP

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-11-05 17:00:00.000000

题干结构化 §12.3 N5(修订):外部 Agent 可经 MCP 发起变式 / 命题等生成操作,
生成的题目记 created_via='mcp',便于老师筛选与清理。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d8e9f0a1b2c3"
down_revision: Union[str, Sequence[str], None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("questions") as batch_op:
        batch_op.add_column(sa.Column("created_via", sa.String(length=16), nullable=True))
        batch_op.create_index(batch_op.f("ix_questions_created_via"), ["created_via"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("questions") as batch_op:
        batch_op.drop_index(batch_op.f("ix_questions_created_via"))
        batch_op.drop_column("created_via")
