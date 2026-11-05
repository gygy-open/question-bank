"""struct element groups

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-11-05 15:00:00.000000

元素组(规格 docs/specs/question-structure.md §12.3 N2):几条条件作为整体,可整组替换。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, Sequence[str], None] = "b6c7d8e9f0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "struct_element_groups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("replaceable", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"], ["struct_runs.id"], name=op.f("fk_struct_element_groups_run_id_struct_runs"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_struct_element_groups")),
    )
    op.create_index(op.f("ix_struct_element_groups_id"), "struct_element_groups", ["id"], unique=False)
    op.create_index("ix_struct_element_groups_run_ordinal", "struct_element_groups", ["run_id", "ordinal"], unique=False)
    op.create_table(
        "struct_element_group_items",
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("element_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["group_id"], ["struct_element_groups.id"],
            name=op.f("fk_struct_element_group_items_group_id_struct_element_groups"), ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["element_id"], ["struct_elements.id"],
            name=op.f("fk_struct_element_group_items_element_id_struct_elements"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("group_id", "element_id", name=op.f("pk_struct_element_group_items")),
    )


def downgrade() -> None:
    op.drop_table("struct_element_group_items")
    op.drop_table("struct_element_groups")
