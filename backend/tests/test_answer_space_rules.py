import pytest

from app.core.permissions import SubjectRole
from app.core.security import create_access_token
from app.models.question import QuestionType
from app.models.subject import Subject
from app.models.user import User
from app.services.answer_space import (
    DEFAULT_RULES,
    merge_rules,
    resolve_answer_space_props,
    resolve_answer_space_props_or_fallback,
)

API = "/api/v1"

FREE = QuestionType.FREE_RESPONSE.value
SINGLE = QuestionType.SINGLE_CHOICE.value
FILL = QuestionType.FILL_IN_THE_BLANK.value


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=user.id)}"}


# --------------------------------------------------------------------------- #
# 纯函数解析
# --------------------------------------------------------------------------- #
def test_choice_types_get_no_answer_space_by_default():
    assert resolve_answer_space_props(q_type=SINGLE, score=3) is None
    assert resolve_answer_space_props(q_type=QuestionType.TRUE_FALSE.value, score=2) is None


def test_free_response_lines_scale_with_score_and_clamp():
    assert resolve_answer_space_props(q_type=FREE, score=None) == {"lines": 2, "style": "lined"}
    assert resolve_answer_space_props(q_type=FREE, score=6) == {"lines": 5, "style": "lined"}
    # 上限封顶：60 分作文不会撑出 48 行。
    assert resolve_answer_space_props(q_type=FREE, score=60) == {"lines": 20, "style": "lined"}
    # 下限兜底：1 分题至少给 min_lines。
    assert resolve_answer_space_props(q_type=FREE, score=1) == {"lines": 2, "style": "lined"}


def test_fill_in_the_blank_is_shorter_than_free_response():
    fill = resolve_answer_space_props(q_type=FILL, score=4)
    free = resolve_answer_space_props(q_type=FREE, score=4)
    assert fill is not None and free is not None
    assert fill["lines"] < free["lines"]
    assert fill["style"] == "blank"


def test_explicit_insert_on_choice_type_still_gets_usable_props():
    assert resolve_answer_space_props_or_fallback(q_type=SINGLE, score=3) == {
        "lines": 2, "style": "lined",
    }
    assert resolve_answer_space_props_or_fallback(q_type=None, score=10) == {
        "lines": 8, "style": "lined",
    }


# --------------------------------------------------------------------------- #
# 学科覆盖合并
# --------------------------------------------------------------------------- #
def test_override_merges_per_field_and_keeps_other_types_on_defaults():
    rules = merge_rules({FREE: {"lines_per_score": 2.0, "max_lines": 40}})
    assert rules[FREE].lines_per_score == 2.0
    assert rules[FREE].max_lines == 40
    assert rules[FREE].min_lines == DEFAULT_RULES[FREE].min_lines
    assert rules[SINGLE] == DEFAULT_RULES[SINGLE]
    assert resolve_answer_space_props(q_type=FREE, score=6, rules=rules) == {
        "lines": 12, "style": "lined",
    }


def test_dirty_override_falls_back_instead_of_breaking_paper_generation():
    rules = merge_rules({FREE: {"style": "dotted", "min_lines": "x", "lines_per_score": -3}})
    assert rules[FREE] == DEFAULT_RULES[FREE]
    assert merge_rules("not-a-dict") == DEFAULT_RULES
    # max_lines 低于 min_lines 时收窄到 min_lines，不产生空区间。
    assert merge_rules({FREE: {"min_lines": 6, "max_lines": 2}})[FREE].max_lines == 6


def test_choice_type_can_be_enabled_by_subject_override():
    rules = merge_rules({SINGLE: {"enabled": True, "min_lines": 1}})
    assert resolve_answer_space_props(q_type=SINGLE, score=3, rules=rules) == {
        "lines": 1, "style": "blank",
    }


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
async def _seed(db_session) -> tuple[User, Subject]:
    actor = User(username="rule-editor", full_name="Rule Editor", hashed_password="x")
    subject = Subject(name="语文", slug="rules-chinese")
    db_session.add_all([actor, subject])
    await db_session.commit()
    return actor, subject


@pytest.mark.asyncio
async def test_rules_endpoint_roundtrip_and_reset(client, db_session, grant_role):
    actor, subject = await _seed(db_session)
    await grant_role(actor, subject, SubjectRole.MANAGER)
    headers = _auth(actor)

    initial = await client.get(f"{API}/subjects/{subject.id}/answer-space-rules", headers=headers)
    assert initial.status_code == 200, initial.text
    assert initial.json()["is_custom"] is False
    assert initial.json()["rules"][FREE]["lines_per_score"] == DEFAULT_RULES[FREE].lines_per_score

    payload = {
        "rules": {
            FREE: {
                "enabled": True, "min_lines": 3, "lines_per_score": 1.5,
                "max_lines": 30, "style": "lined",
            }
        }
    }
    saved = await client.put(
        f"{API}/subjects/{subject.id}/answer-space-rules", json=payload, headers=headers
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["is_custom"] is True
    assert saved.json()["rules"][FREE]["lines_per_score"] == 1.5
    # 未提交的题型保持代码默认值。
    assert saved.json()["rules"][SINGLE]["enabled"] is False

    reread = await client.get(f"{API}/subjects/{subject.id}/answer-space-rules", headers=headers)
    assert reread.json()["rules"][FREE]["min_lines"] == 3

    reset = await client.delete(
        f"{API}/subjects/{subject.id}/answer-space-rules", headers=headers
    )
    assert reset.status_code == 200, reset.text
    assert reset.json()["is_custom"] is False
    assert reset.json()["rules"][FREE]["min_lines"] == DEFAULT_RULES[FREE].min_lines


@pytest.mark.asyncio
async def test_rules_endpoint_rejects_invalid_range_and_style(client, db_session, grant_role):
    actor, subject = await _seed(db_session)
    await grant_role(actor, subject, SubjectRole.MANAGER)
    headers = _auth(actor)

    bad_range = await client.put(
        f"{API}/subjects/{subject.id}/answer-space-rules",
        json={"rules": {FREE: {
            "enabled": True, "min_lines": 9, "lines_per_score": 1,
            "max_lines": 2, "style": "lined",
        }}},
        headers=headers,
    )
    assert bad_range.status_code == 422, bad_range.text

    bad_lines = await client.put(
        f"{API}/subjects/{subject.id}/answer-space-rules",
        json={"rules": {FREE: {
            "enabled": True, "min_lines": 0, "lines_per_score": 1,
            "max_lines": 5, "style": "lined",
        }}},
        headers=headers,
    )
    assert bad_lines.status_code == 422, bad_lines.text
