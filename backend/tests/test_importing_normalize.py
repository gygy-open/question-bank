"""Phase 1 单测:统一归一化出口 QuestionImporter(worker / batch-legacy 共用)。"""

import json

from sqlalchemy import select

from app.models.question import Question, QuestionStatus, QuestionType
from app.models.user import User
from app.services.importing.contracts import ImportDefaults
from app.services.importing.normalize import (
    QuestionImporter,
    _coerce_kp_ids,
    _coerce_q_type,
    _coerce_status,
    _resolve_ai_tags,
)


def test_coerce_q_type_from_legacy_strings():
    assert _coerce_q_type("multiple_choice") == QuestionType.MULTIPLE_CHOICE
    assert _coerce_q_type("填空题") == QuestionType.FILL_IN_THE_BLANK
    assert _coerce_q_type("解答") == QuestionType.FREE_RESPONSE
    assert _coerce_q_type(None) == QuestionType.SINGLE_CHOICE
    # 已是枚举则原样返回。
    assert _coerce_q_type(QuestionType.TRUE_FALSE) == QuestionType.TRUE_FALSE


def test_coerce_status_falls_back_on_unknown():
    assert _coerce_status(None, QuestionStatus.PENDING) == QuestionStatus.PENDING
    assert _coerce_status("draft", QuestionStatus.PENDING) == QuestionStatus.DRAFT
    assert _coerce_status("bogus", QuestionStatus.PENDING) == QuestionStatus.PENDING


def test_coerce_kp_ids_skips_non_ints():
    assert _coerce_kp_ids(["1", 2, "x", None]) == [1, 2]
    assert _coerce_kp_ids(None) == []


def test_resolve_ai_tags_prefers_explicit_over_tags():
    assert _resolve_ai_tags({"ai_suggested_tags": {"a": ["x"]}}) == {"a": ["x"]}
    assert _resolve_ai_tags({"tags": ["y"]}) == {"ai_extracted": ["y"]}
    assert _resolve_ai_tags({}) is None


async def test_import_batch_worker_style_dicts(db_session):
    """worker 传入 AI 抽取的裸 dict(q_type 为字符串、tags 待转 ai_suggested_tags)。"""
    user = User(username="importer-unit", full_name="U", hashed_password="x", is_active=True)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    raws = [
        {
            "content": "计算 **1 + 1**。",
            "q_type": "free_response",
            "answer": "答案是 $2$。",
            "difficulty": 1,
            "tags": ["算术"],
        },
        {
            "content": "无法确定答案的选择题",
            "q_type": "single_choice",
            "options": ["A. 甲", "B. 乙"],
            "answer": "见解析",
        },
    ]

    report = await QuestionImporter().import_batch(
        db_session,
        raws,
        user_id=user.id,
        import_task_id=None,
        defaults=ImportDefaults(subject_id=None, status=QuestionStatus.PENDING, source="unit.md"),
    )

    assert report.saved_count == 1
    assert report.failed_count == 1
    assert report.failed[0].index == 1
    assert "无法解析" in report.failed[0].message

    rows = (await db_session.execute(select(Question))).scalars().all()
    assert len(rows) == 1
    answer = json.loads(rows[0].answer) if isinstance(rows[0].answer, str) else rows[0].answer
    assert answer["kind"] == "free_response"
    assert rows[0].source == "unit.md"
