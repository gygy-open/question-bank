"""drop obsolete system settings

Revision ID: 326519e83a77
Revises: cc9f4fd05314
Create Date: 2026-08-14 17:45:09.269516

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '326519e83a77'
down_revision: Union[str, Sequence[str], None] = 'cc9f4fd05314'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 这些键已废弃：GEMINI_* 为旧供应商配置；三个 PROMPT 已改为硬编码/学科分层。
# 作为数据迁移一次性清理，不再依赖 initial_data.py。
OBSOLETE_KEYS = [
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "GEMINI_VISION_MODEL",
    "GEMINI_PROMPT",
    "CHAT_SYSTEM_PROMPT",
    "AI_EXTRACT_PROMPT",
    "AI_SOLVE_PROMPT",
]


def upgrade() -> None:
    """Delete obsolete rows from system_settings."""
    bind = op.get_bind()
    # sa.table/column so the reserved word ``key`` is quoted per-dialect
    # (backticks on MySQL); a raw SQL string breaks on MySQL.
    system_settings = sa.table("system_settings", sa.column("key", sa.String))
    bind.execute(
        system_settings.delete().where(system_settings.c.key.in_(OBSOLETE_KEYS))
    )


def downgrade() -> None:
    """No-op: original values are user data and cannot be restored."""


