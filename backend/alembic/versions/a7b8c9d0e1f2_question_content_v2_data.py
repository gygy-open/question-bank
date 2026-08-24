"""question content v2 data migration

题目内容 v1 → v2 的**数据** revision(独立于结构 revision ``f1a2b3c4d5e6``):

1. 建无 FK 归档表 ``questions_content_archive_v1``(不进 ORM),快照 v1 原文。
2. 以 ``content_schema_version < 1`` 为幂等闸门,分批:
   - 把尚未归档的 v0 行原文写入归档表;
   - 调 ``app.services.question_content_v1`` 把六个内容字段 + options 转成 v2 JSON,
     置 ``content_schema_version = 1``、``needs_review`` 依转换结果;
   - ``legacy_unresolved`` 的选择/判断答案:原答案原文并入 ``analysis``(不覆盖原解析)。
3. 末尾把 ``content_schema_version`` 的 server_default 从 0 改为 1(与 ORM 对齐)。

MySQL DDL 隐式 commit、无整体事务;靠 "建表 IF NOT EXISTS + ``version < 1`` +
``NOT IN archive``" 的幂等设计支持中断后重跑,而非依赖事务回滚。全程 Core /
``sa.table``,不引用 ORM 模型;JSON 参数在 SQLite / MySQL 一致工作。

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e6
Create Date: 2026-08-24 00:10:00.000000

"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional, Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import LONGTEXT

from app.services.question_content_v1 import (
    convert_answer,
    convert_options,
    markdown_to_rich_doc,
    merge_legacy_answer_into_analysis,
)


# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ARCHIVE_TABLE = "questions_content_archive_v1"
_BATCH_SIZE = 500
# TEXT 列里存的 RichDoc / AnswerSpec 内容字段(区别于真正的 JSON 列 options)。
_CONTENT_COLUMNS: tuple[str, ...] = ("content", "answer", "thinking", "analysis", "summary")
_EMPTY_DOC: dict[str, Any] = {"type": "doc", "content": [{"type": "paragraph"}]}


def _rich_type(dialect_name: str) -> sa.types.TypeEngine:
    return LONGTEXT() if dialect_name == "mysql" else sa.Text()


def _questions_table() -> sa.Table:
    """``questions`` 的最小 Core 投影(只含本迁移用到的列)。"""
    return sa.table(
        "questions",
        sa.column("id", sa.Integer),
        sa.column("q_type", sa.String),
        sa.column("status", sa.String),
        sa.column("content", sa.Text),
        sa.column("options", sa.JSON),
        sa.column("answer", sa.Text),
        sa.column("thinking", sa.Text),
        sa.column("analysis", sa.Text),
        sa.column("summary", sa.Text),
        sa.column("content_schema_version", sa.SmallInteger),
        sa.column("needs_review", sa.Boolean),
    )


def _archive_table() -> sa.Table:
    return sa.table(
        ARCHIVE_TABLE,
        sa.column("question_id", sa.Integer),
        sa.column("content", sa.Text),
        sa.column("answer", sa.Text),
        sa.column("thinking", sa.Text),
        sa.column("analysis", sa.Text),
        sa.column("summary", sa.Text),
        sa.column("options", sa.JSON),
        sa.column("archived_at", sa.DateTime),
    )


def _ensure_archive_table(bind: sa.engine.Connection) -> None:
    """建归档表(已存在则跳过),支持中断后重跑。"""
    inspector = sa.inspect(bind)
    if ARCHIVE_TABLE in inspector.get_table_names():
        return
    rich_type = _rich_type(bind.dialect.name)
    op.create_table(
        ARCHIVE_TABLE,
        sa.Column("question_id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("content", rich_type, nullable=True),
        sa.Column("answer", rich_type, nullable=True),
        sa.Column("thinking", rich_type, nullable=True),
        sa.Column("analysis", rich_type, nullable=True),
        sa.Column("summary", rich_type, nullable=True),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
    )


def _dumps(value: Any) -> Optional[str]:
    """把 RichDoc / AnswerSpec 序列化为 JSON 字符串;None → None。"""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _archived_ids(bind: sa.engine.Connection, archive: sa.Table, ids: list[int]) -> set[int]:
    if not ids:
        return set()
    rows = bind.execute(
        sa.select(archive.c.question_id).where(archive.c.question_id.in_(ids))
    ).fetchall()
    return {r[0] for r in rows}


def _archive_batch(bind: sa.engine.Connection, archive: sa.Table, rows: Sequence[Any]) -> None:
    """把 rows 中尚未归档的行快照入归档表。"""
    existing = _archived_ids(bind, archive, [r.id for r in rows])
    payload = [
        {
            "question_id": r.id,
            "content": r.content,
            "answer": r.answer,
            "thinking": r.thinking,
            "analysis": r.analysis,
            "summary": r.summary,
            "options": r.options,
            "archived_at": datetime.utcnow(),
        }
        for r in rows
        if r.id not in existing
    ]
    if payload:
        bind.execute(archive.insert(), payload)


def _convert_batch(bind: sa.engine.Connection, questions: sa.Table, rows: Sequence[Any]) -> None:
    """逐行转换写回 questions,成功即置 version=1、needs_review 依结果。"""
    for r in rows:
        options = convert_options(r.options)
        content_doc = markdown_to_rich_doc(r.content)
        thinking_doc = markdown_to_rich_doc(r.thinking)
        analysis_doc = markdown_to_rich_doc(r.analysis)
        summary_doc = markdown_to_rich_doc(r.summary)
        answer_spec, needs_review = convert_answer(r.q_type, r.answer, options)
        answer_missing = answer_spec is None
        needs_review = needs_review or (
            answer_missing and r.status in {"pending", "published"}
        )

        if answer_spec and answer_spec.get("kind") == "legacy_unresolved":
            # 原答案原文并入 analysis(不覆盖既有解析)。
            analysis_doc = merge_legacy_answer_into_analysis(analysis_doc, r.answer)

        bind.execute(
            questions.update()
            .where(questions.c.id == r.id)
            .values(
                content=_dumps(content_doc if content_doc is not None else _EMPTY_DOC),
                options=options if options else None,
                answer=_dumps(answer_spec),
                thinking=_dumps(thinking_doc),
                analysis=_dumps(analysis_doc),
                summary=_dumps(summary_doc),
                content_schema_version=1,
                needs_review=bool(needs_review),
            )
        )


def _set_version_default(bind: sa.engine.Connection, value: str) -> None:
    """改 content_schema_version 的 server_default(SQLite 重建 / MySQL 原地)。"""
    with op.batch_alter_table("questions", schema=None) as batch:
        batch.alter_column(
            "content_schema_version",
            existing_type=sa.SmallInteger(),
            existing_nullable=False,
            server_default=value,
        )


def upgrade() -> None:
    bind = op.get_bind()
    _ensure_archive_table(bind)
    questions = _questions_table()
    archive = _archive_table()

    # 闸门 version < 1;每批转换后这些行变 1,自然滚动到下一批,可中断重跑。
    while True:
        rows = bind.execute(
            sa.select(
                questions.c.id,
                questions.c.q_type,
                questions.c.status,
                questions.c.content,
                questions.c.options,
                questions.c.answer,
                questions.c.thinking,
                questions.c.analysis,
                questions.c.summary,
            )
            .where(questions.c.content_schema_version < 1)
            .order_by(questions.c.id)
            .limit(_BATCH_SIZE)
        ).fetchall()
        if not rows:
            break
        _archive_batch(bind, archive, rows)
        _convert_batch(bind, questions, rows)

    # 存量清零后,新行默认即 v1(与 ORM SCHEMA_VERSION=1 对齐)。
    _set_version_default(bind, "1")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if ARCHIVE_TABLE in inspector.get_table_names():
        questions = _questions_table()
        archive = _archive_table()
        last_id = -1
        while True:
            rows = bind.execute(
                sa.select(archive)
                .where(archive.c.question_id > last_id)
                .order_by(archive.c.question_id)
                .limit(_BATCH_SIZE)
            ).fetchall()
            if not rows:
                break
            for r in rows:
                last_id = r.question_id
                # question 仍存在才还原;不存在的 update 影响 0 行。
                bind.execute(
                    questions.update()
                    .where(questions.c.id == r.question_id)
                    .values(
                        content=r.content,
                        options=r.options,
                        answer=r.answer,
                        thinking=r.thinking,
                        analysis=r.analysis,
                        summary=r.summary,
                        content_schema_version=0,
                        needs_review=False,
                    )
                )

    # 归档表保留(不 drop),供后续独立 revision 清理。
    _set_version_default(bind, "0")
