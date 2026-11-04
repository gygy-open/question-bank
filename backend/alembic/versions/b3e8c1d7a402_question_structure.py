"""question structure: elements, asks, steps

Revision ID: b3e8c1d7a402
Revises: a7c9e1f3b5d2
Create Date: 2026-11-04 09:00:00.000000

拆解结果旁挂在 questions 上，不改动 questions 的任何字段。一次拆解是一个 run，
同题可以有多次，互不覆盖；元素、设问、步骤、参数都挂在 run 上。

词表（element_roles / element_types / solving_methods）用外键而不是数据库枚举：
它们是会持续增长的数据，做成 ENUM 就意味着加一个类型要发一次版、写一次
batch_alter。初始词表由 scripts/seed_struct_vocabulary.py 灌入，迁移只建表。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b3e8c1d7a402"
down_revision: Union[str, Sequence[str], None] = "a7c9e1f3b5d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------- 词表 ----------
    op.create_table(
        "element_roles",
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_element_roles")),
    )

    op.create_table(
        "element_types",
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("subject", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_element_types")),
        sa.UniqueConstraint("subject", "action", name=op.f("uq_element_types_subject_action")),
    )

    op.create_table(
        "solving_methods",
        sa.Column("code", sa.String(length=48), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("parent_code", sa.String(length=48), nullable=True),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ["parent_code"],
            ["solving_methods.code"],
            name=op.f("fk_solving_methods_parent_code_solving_methods"),
        ),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_solving_methods")),
    )

    op.create_table(
        "struct_vocabulary_meta",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_struct_vocabulary_meta")),
    )

    # ---------- 拆解快照 ----------
    op.create_table(
        "question_struct_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=True),
        sa.Column("rev", sa.Integer(), nullable=False),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("prompt_version", sa.String(length=32), nullable=True),
        sa.Column("vocabulary_version", sa.String(length=32), nullable=True),
        sa.Column("state", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["question_id"], ["questions.id"], name=op.f("fk_question_struct_runs_question_id_questions")
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"], ["subjects.id"], name=op.f("fk_question_struct_runs_subject_id_subjects")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_struct_runs")),
        sa.UniqueConstraint("question_id", "rev", name=op.f("uq_question_struct_runs_question_rev")),
    )
    op.create_index(
        op.f("ix_question_struct_runs_id"), "question_struct_runs", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_question_struct_runs_question_id"),
        "question_struct_runs",
        ["question_id"],
        unique=False,
    )
    op.create_index(
        "ix_question_struct_runs_subject_state",
        "question_struct_runs",
        ["subject_id", "state"],
        unique=False,
    )

    # ---------- 材料 / 元素组 ----------
    op.create_table(
        "question_struct_materials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("span_start", sa.Integer(), nullable=True),
        sa.Column("span_end", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="ai", nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["question_struct_runs.id"],
            name=op.f("fk_question_struct_materials_run_id_question_struct_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_struct_materials")),
    )
    op.create_index(
        op.f("ix_question_struct_materials_id"), "question_struct_materials", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_question_struct_materials_run_id"),
        "question_struct_materials",
        ["run_id"],
        unique=False,
    )

    op.create_table(
        "question_struct_element_groups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["question_struct_runs.id"],
            name=op.f("fk_question_struct_element_groups_run_id_question_struct_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_struct_element_groups")),
    )
    op.create_index(
        op.f("ix_question_struct_element_groups_id"),
        "question_struct_element_groups",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_question_struct_element_groups_run_id"),
        "question_struct_element_groups",
        ["run_id"],
        unique=False,
    )

    # ---------- 元素 ----------
    op.create_table(
        "question_struct_elements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("element_type", sa.String(length=32), nullable=True),
        sa.Column("group_id", sa.Integer(), nullable=True),
        sa.Column("material_id", sa.Integer(), nullable=True),
        sa.Column("span_start", sa.Integer(), nullable=True),
        sa.Column("span_end", sa.Integer(), nullable=True),
        sa.Column("atomic_ok", sa.Boolean(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="ai", nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["question_struct_runs.id"],
            name=op.f("fk_question_struct_elements_run_id_question_struct_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role"], ["element_roles.code"], name=op.f("fk_question_struct_elements_role_element_roles")
        ),
        sa.ForeignKeyConstraint(
            ["element_type"],
            ["element_types.code"],
            name=op.f("fk_question_struct_elements_element_type_element_types"),
        ),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["question_struct_element_groups.id"],
            name=op.f("fk_question_struct_elements_group_id_question_struct_element_groups"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["material_id"],
            ["question_struct_materials.id"],
            name=op.f("fk_question_struct_elements_material_id_question_struct_materials"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_struct_elements")),
    )
    op.create_index(
        op.f("ix_question_struct_elements_id"), "question_struct_elements", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_question_struct_elements_role"), "question_struct_elements", ["role"], unique=False
    )
    op.create_index(
        "ix_question_struct_elements_run_ordinal",
        "question_struct_elements",
        ["run_id", "ordinal"],
        unique=False,
    )
    op.create_index(
        "ix_question_struct_elements_type",
        "question_struct_elements",
        ["element_type"],
        unique=False,
    )

    # ---------- 设问 ----------
    op.create_table(
        "question_struct_asks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("target", sa.String(length=16), nullable=False),
        sa.Column("points", sa.Float(), nullable=True),
        sa.Column("span_start", sa.Integer(), nullable=True),
        sa.Column("span_end", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="ai", nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["question_struct_runs.id"],
            name=op.f("fk_question_struct_asks_run_id_question_struct_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_struct_asks")),
    )
    op.create_index(op.f("ix_question_struct_asks_id"), "question_struct_asks", ["id"], unique=False)
    op.create_index(
        "ix_question_struct_asks_run_ordinal",
        "question_struct_asks",
        ["run_id", "ordinal"],
        unique=False,
    )

    op.create_table(
        "question_struct_ask_elements",
        sa.Column("ask_id", sa.Integer(), nullable=False),
        sa.Column("element_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["ask_id"],
            ["question_struct_asks.id"],
            name=op.f("fk_question_struct_ask_elements_ask_id_question_struct_asks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["element_id"],
            ["question_struct_elements.id"],
            name=op.f("fk_question_struct_ask_elements_element_id_question_struct_elements"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "ask_id", "element_id", name=op.f("pk_question_struct_ask_elements")
        ),
    )

    # ---------- 参数槽 ----------
    op.create_table(
        "question_struct_params",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("element_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.Column("value_text", sa.String(length=255), nullable=False),
        sa.Column("slot_kind", sa.String(length=16), nullable=True),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column("replaceable", sa.Boolean(), server_default="1", nullable=False),
        sa.ForeignKeyConstraint(
            ["element_id"],
            ["question_struct_elements.id"],
            name=op.f("fk_question_struct_params_element_id_question_struct_elements"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_struct_params")),
    )
    op.create_index(
        op.f("ix_question_struct_params_id"), "question_struct_params", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_question_struct_params_element_id"),
        "question_struct_params",
        ["element_id"],
        unique=False,
    )

    # ---------- 步骤与产出 ----------
    op.create_table(
        "question_struct_steps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("ask_id", sa.Integer(), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(length=48), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("is_breakthrough", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("span_start", sa.Integer(), nullable=True),
        sa.Column("span_end", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="ai", nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["question_struct_runs.id"],
            name=op.f("fk_question_struct_steps_run_id_question_struct_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ask_id"],
            ["question_struct_asks.id"],
            name=op.f("fk_question_struct_steps_ask_id_question_struct_asks"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["method"],
            ["solving_methods.code"],
            name=op.f("fk_question_struct_steps_method_solving_methods"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_struct_steps")),
    )
    op.create_index(op.f("ix_question_struct_steps_id"), "question_struct_steps", ["id"], unique=False)
    op.create_index(
        "ix_question_struct_steps_run_ordinal",
        "question_struct_steps",
        ["run_id", "ordinal"],
        unique=False,
    )
    op.create_index(
        "ix_question_struct_steps_method", "question_struct_steps", ["method"], unique=False
    )

    op.create_table(
        "question_struct_produces",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("step_id", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.ForeignKeyConstraint(
            ["step_id"],
            ["question_struct_steps.id"],
            name=op.f("fk_question_struct_produces_step_id_question_struct_steps"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_struct_produces")),
    )
    op.create_index(
        op.f("ix_question_struct_produces_id"), "question_struct_produces", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_question_struct_produces_step_id"),
        "question_struct_produces",
        ["step_id"],
        unique=False,
    )

    op.create_table(
        "question_struct_step_elements",
        sa.Column("step_id", sa.Integer(), nullable=False),
        sa.Column("element_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["step_id"],
            ["question_struct_steps.id"],
            name=op.f("fk_question_struct_step_elements_step_id_question_struct_steps"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["element_id"],
            ["question_struct_elements.id"],
            name=op.f("fk_question_struct_step_elements_element_id_question_struct_elements"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "step_id", "element_id", name=op.f("pk_question_struct_step_elements")
        ),
    )

    op.create_table(
        "question_struct_step_produces",
        sa.Column("step_id", sa.Integer(), nullable=False),
        sa.Column("produce_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["step_id"],
            ["question_struct_steps.id"],
            name=op.f("fk_question_struct_step_produces_step_id_question_struct_steps"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["produce_id"],
            ["question_struct_produces.id"],
            name=op.f("fk_question_struct_step_produces_produce_id_question_struct_produces"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "step_id", "produce_id", name=op.f("pk_question_struct_step_produces")
        ),
    )

    # ---------- 常见错误 ----------
    op.create_table(
        "question_struct_misconceptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("step_id", sa.Integer(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("error_rate", sa.Float(), nullable=True),
        sa.Column("sample_size", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_question_struct_misconceptions_question_id_questions"),
        ),
        sa.ForeignKeyConstraint(
            ["step_id"],
            ["question_struct_steps.id"],
            name=op.f("fk_question_struct_misconceptions_step_id_question_struct_steps"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_question_struct_misconceptions")),
    )
    op.create_index(
        op.f("ix_question_struct_misconceptions_id"),
        "question_struct_misconceptions",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_question_struct_misconceptions_question_id"),
        "question_struct_misconceptions",
        ["question_id"],
        unique=False,
    )


def downgrade() -> None:
    for table in (
        "question_struct_misconceptions",
        "question_struct_step_produces",
        "question_struct_step_elements",
        "question_struct_produces",
        "question_struct_steps",
        "question_struct_params",
        "question_struct_ask_elements",
        "question_struct_asks",
        "question_struct_elements",
        "question_struct_element_groups",
        "question_struct_materials",
        "question_struct_runs",
        "struct_vocabulary_meta",
        "solving_methods",
        "element_types",
        "element_roles",
    ):
        op.drop_table(table)
