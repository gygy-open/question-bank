"""question content v2 structure

题目内容 v2 的**结构** revision(不改数据):
- content / answer / thinking / analysis / summary:``TEXT`` → MySQL ``LONGTEXT``
  (SQLite 保持 ``TEXT``,方言感知)。
- 新增 ``content_schema_version SMALLINT NOT NULL DEFAULT 0``(存量行标记未迁移)。
- 新增 ``needs_review BOOL NOT NULL DEFAULT 0``(迁移无法解析行的人工复核标记)。

数据转换在下一个独立的 data revision 完成;此处仅动结构。SQLite 走 batch 重建,
MySQL 走原地 ALTER,二者都兼容。

Revision ID: f1a2b3c4d5e6
Revises: 326519e83a77
Create Date: 2026-08-24 00:00:00.000000

"""
from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import LONGTEXT


# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "326519e83a77"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 富文本内容列名(存 RichDoc / AnswerSpec 的 JSON 字符串)。
_RICH_COLUMNS: tuple[str, ...] = ("content", "answer", "thinking", "analysis", "summary")


def _rich_type(dialect_name: str) -> sa.types.TypeEngine:
    """MySQL → LONGTEXT;其它(SQLite)→ TEXT。"""
    return LONGTEXT() if dialect_name == "mysql" else sa.Text()


def upgrade() -> None:
    bind = op.get_bind()
    rich_type = _rich_type(bind.dialect.name)

    with op.batch_alter_table("questions", schema=None) as batch:
        for name in _RICH_COLUMNS:
            batch.alter_column(
                name,
                existing_type=sa.Text(),
                type_=rich_type,
                existing_nullable=(name != "content"),
            )
        batch.add_column(
            sa.Column(
                "content_schema_version",
                sa.SmallInteger(),
                nullable=False,
                server_default="0",
            )
        )
        batch.add_column(
            sa.Column(
                "needs_review",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    rich_type = _rich_type(bind.dialect.name)

    with op.batch_alter_table("questions", schema=None) as batch:
        batch.drop_column("needs_review")
        batch.drop_column("content_schema_version")
        for name in _RICH_COLUMNS:
            batch.alter_column(
                name,
                existing_type=rich_type,
                type_=sa.Text(),
                existing_nullable=(name != "content"),
            )
