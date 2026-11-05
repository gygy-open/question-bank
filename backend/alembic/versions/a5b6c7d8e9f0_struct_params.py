"""struct_params: replaceable parameter slots of a decomposition

Revision ID: a5b6c7d8e9f0
Revises: f4a5b6c7d8e9
Create Date: 2026-11-05 13:00:00.000000

参数槽(规格 docs/specs/question-structure.md §12.3 N1):题干中可替换的值,按 stem_text
区间定位,挂在条件或设问上,随快照继承;用于按参数生成变式题。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a5b6c7d8e9f0"
down_revision: Union[str, Sequence[str], None] = "f4a5b6c7d8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "struct_params",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("element_id", sa.Integer(), nullable=True),
        sa.Column("ask_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("slot_kind", sa.String(length=16), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("span_start", sa.Integer(), nullable=True),
        sa.Column("span_end", sa.Integer(), nullable=True),
        sa.Column("domain", sa.Text(), nullable=True),
        sa.Column("domain_confirmed", sa.Boolean(), nullable=False),
        sa.Column("replaceable", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"], ["struct_runs.id"], name=op.f("fk_struct_params_run_id_struct_runs"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["element_id"], ["struct_elements.id"], name=op.f("fk_struct_params_element_id_struct_elements"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ask_id"], ["struct_asks.id"], name=op.f("fk_struct_params_ask_id_struct_asks"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_struct_params")),
    )
    op.create_index(op.f("ix_struct_params_id"), "struct_params", ["id"], unique=False)
    op.create_index(op.f("ix_struct_params_element_id"), "struct_params", ["element_id"], unique=False)
    op.create_index(op.f("ix_struct_params_ask_id"), "struct_params", ["ask_id"], unique=False)
    op.create_index("ix_struct_params_run_ordinal", "struct_params", ["run_id", "ordinal"], unique=False)


def downgrade() -> None:
    op.drop_table("struct_params")
