"""chat_messages: JSON 'null' -> SQL NULL

tool_calls/images were stored as the JSON literal 'null' when None was passed
explicitly, which made user messages fail the transcript's `tool_calls IS NULL`
filter. The model now uses none_as_null=True; this normalizes existing rows.

Revision ID: b8d2e4f6a1c3
Revises: a7c1d9e3f5b2
Create Date: 2026-10-27 20:45:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'b8d2e4f6a1c3'
down_revision: Union[str, Sequence[str], None] = 'a7c1d9e3f5b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    is_mysql = op.get_bind().dialect.name == "mysql"
    for column in ("tool_calls", "images"):
        cond = f"JSON_TYPE({column}) = 'NULL'" if is_mysql else f"{column} = 'null'"
        op.execute(f"UPDATE chat_messages SET {column} = NULL WHERE {column} IS NOT NULL AND {cond}")


def downgrade() -> None:
    pass
