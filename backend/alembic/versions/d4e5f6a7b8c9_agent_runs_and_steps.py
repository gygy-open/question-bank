"""agent runs and steps

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-09 12:00:00.000000

Agent 运行记录,纯结构变更:
  * agent_runs / agent_steps:一轮工具循环及其每一步,用于排障、审计与用量统计。
  * chat_messages 增加 run_id / tool_call_id,让工具调用与工具结果能真正落库 ——
    此前它们只存在于内存,重建历史时被跳过,导致多轮对话上下文断裂。

存量数据安全:旧代码从未写入过带 tool_calls 的 assistant 行(那段 create 一直是注释掉的),
因此没有孤儿工具消息需要回填。

JSON 列一律用 sa.JSON():SQLite(测试/桌面)与 MySQL(服务端)双目标,不用方言专有类型。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=True),
        sa.Column("surface", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("model_id", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.ForeignKeyConstraint(
            ["session_id"], ["chat_sessions.id"],
            name=op.f("fk_agent_runs_session_id_chat_sessions"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name=op.f("fk_agent_runs_user_id_user"),
        ),
        sa.ForeignKeyConstraint(
            ["subject_id"], ["subjects.id"], name=op.f("fk_agent_runs_subject_id_subjects"),
        ),
        sa.ForeignKeyConstraint(
            ["model_id"], ["ai_models.id"], name=op.f("fk_agent_runs_model_id_ai_models"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_runs")),
    )
    op.create_index(op.f("ix_agent_runs_session_id"), "agent_runs", ["session_id"], unique=False)
    op.create_index(op.f("ix_agent_runs_user_id"), "agent_runs", ["user_id"], unique=False)

    op.create_table(
        "agent_steps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("tool_name", sa.String(length=64), nullable=True),
        sa.Column("args", sa.JSON(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"], ["agent_runs.id"],
            name=op.f("fk_agent_steps_run_id_agent_runs"), ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_steps")),
    )
    op.create_index(op.f("ix_agent_steps_id"), "agent_steps", ["id"], unique=False)
    op.create_index(op.f("ix_agent_steps_run_id"), "agent_steps", ["run_id"], unique=False)

    with op.batch_alter_table("chat_messages") as batch_op:
        batch_op.add_column(sa.Column("tool_call_id", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("run_id", sa.String(length=36), nullable=True))
        batch_op.create_foreign_key(
            op.f("fk_chat_messages_run_id_agent_runs"), "agent_runs", ["run_id"], ["id"]
        )
        batch_op.create_index(op.f("ix_chat_messages_run_id"), ["run_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("chat_messages") as batch_op:
        batch_op.drop_index(op.f("ix_chat_messages_run_id"))
        batch_op.drop_constraint(op.f("fk_chat_messages_run_id_agent_runs"), type_="foreignkey")
        batch_op.drop_column("run_id")
        batch_op.drop_column("tool_call_id")

    # MySQL: 直接 DROP TABLE,不要先单独 drop FK 依赖的索引(会报 1553)。
    op.drop_table("agent_steps")
    op.drop_table("agent_runs")
