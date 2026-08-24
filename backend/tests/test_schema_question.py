import pytest
from pydantic import ValidationError

from app.models.question import QuestionType
from app.schemas.question import QuestionCreate, QuestionUpdate


def doc(text: str) -> dict:
    return {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]}


def blank_doc(*blank_ids: str) -> dict:
    nodes = []
    for i, bid in enumerate(blank_ids):
        nodes.append({"type": "text", "text": f"空{i + 1}"})
        nodes.append({"type": "blank", "attrs": {"blankId": bid}})
    return {"type": "doc", "content": [{"type": "paragraph", "content": nodes}]}


def _options():
    return [
        {"id": "opt_a", "label": "A", "content": doc("甲")},
        {"id": "opt_b", "label": "B", "content": doc("乙")},
    ]


# --------------------------------------------------------------------------- #
# 五种题型:合法创建
# --------------------------------------------------------------------------- #
def test_single_choice_valid():
    q = QuestionCreate(
        content=doc("题干"),
        q_type=QuestionType.SINGLE_CHOICE,
        options=_options(),
        answer={"kind": "single_choice", "correct": "opt_a"},
    )
    assert q.answer.correct == "opt_a"
    assert [o.id for o in q.options] == ["opt_a", "opt_b"]


def test_multiple_choice_valid():
    q = QuestionCreate(
        content=doc("题干"),
        q_type=QuestionType.MULTIPLE_CHOICE,
        options=_options(),
        answer={"kind": "multiple_choice", "correct": ["opt_a", "opt_b"], "grading": "partial"},
    )
    assert q.answer.correct == ["opt_a", "opt_b"]
    assert q.answer.grading == "partial"


def test_true_false_valid_and_ignores_options():
    q = QuestionCreate(
        content=doc("地球是圆的"),
        q_type=QuestionType.TRUE_FALSE,
        options=_options(),  # 非 choice,应被规范化为 None
        answer={"kind": "true_false", "correct": True},
    )
    assert q.answer.correct is True
    assert q.options is None


def test_fill_in_the_blank_valid():
    q = QuestionCreate(
        content=doc("___ 是首都"),
        q_type=QuestionType.FILL_IN_THE_BLANK,
        answer={"kind": "fill_in_the_blank", "blanks": [{"id": "blk_1", "accept": [doc("北京")]}]},
    )
    assert q.answer.blanks[0].id == "blk_1"


def test_free_response_valid():
    q = QuestionCreate(
        content=doc("简答"),
        q_type=QuestionType.FREE_RESPONSE,
        answer={"kind": "free_response", "reference": doc("参考答案")},
    )
    assert q.answer.reference["content"][0]["content"][0]["text"] == "参考答案"


def test_free_response_reference_nullable():
    q = QuestionCreate(
        content=doc("简答"),
        q_type=QuestionType.FREE_RESPONSE,
        answer={"kind": "free_response", "reference": None},
    )
    assert q.answer.reference is None


# --------------------------------------------------------------------------- #
# RichDoc 根节点校验
# --------------------------------------------------------------------------- #
def test_invalid_rich_doc_root_rejected():
    with pytest.raises(ValidationError):
        QuestionCreate(
            content={"type": "paragraph", "content": []},
            q_type=QuestionType.FREE_RESPONSE,
        )


def test_content_required_non_empty():
    with pytest.raises(ValidationError):
        QuestionCreate(content=None, q_type=QuestionType.FREE_RESPONSE)


# --------------------------------------------------------------------------- #
# 交叉校验
# --------------------------------------------------------------------------- #
def test_answer_kind_mismatch_rejected():
    with pytest.raises(ValidationError):
        QuestionCreate(
            content=doc("题干"),
            q_type=QuestionType.SINGLE_CHOICE,
            options=_options(),
            answer={"kind": "true_false", "correct": True},
        )


def test_single_choice_dangling_option_id_rejected():
    with pytest.raises(ValidationError):
        QuestionCreate(
            content=doc("题干"),
            q_type=QuestionType.SINGLE_CHOICE,
            options=_options(),
            answer={"kind": "single_choice", "correct": "opt_missing"},
        )


def test_multiple_choice_dangling_option_id_rejected():
    with pytest.raises(ValidationError):
        QuestionCreate(
            content=doc("题干"),
            q_type=QuestionType.MULTIPLE_CHOICE,
            options=_options(),
            answer={"kind": "multiple_choice", "correct": ["opt_a", "opt_x"]},
        )


def test_duplicate_option_id_rejected():
    with pytest.raises(ValidationError):
        QuestionCreate(
            content=doc("题干"),
            q_type=QuestionType.SINGLE_CHOICE,
            options=[
                {"id": "opt_a", "label": "A", "content": doc("甲")},
                {"id": "opt_a", "label": "B", "content": doc("乙")},
            ],
            answer={"kind": "single_choice", "correct": "opt_a"},
        )


def test_option_id_must_be_non_empty():
    with pytest.raises(ValidationError):
        QuestionCreate(
            content=doc("题干"),
            q_type=QuestionType.SINGLE_CHOICE,
            options=[{"id": "", "label": "A", "content": doc("甲")}],
            answer={"kind": "single_choice", "correct": "opt_a"},
        )


# --------------------------------------------------------------------------- #
# fill:blankId 与 answer blanks 对应
# --------------------------------------------------------------------------- #
def test_fill_blank_ids_match_content_blank_nodes():
    q = QuestionCreate(
        content=blank_doc("blk_1", "blk_2"),
        q_type=QuestionType.FILL_IN_THE_BLANK,
        answer={
            "kind": "fill_in_the_blank",
            "blanks": [
                {"id": "blk_1", "accept": [doc("2")]},
                {"id": "blk_2", "accept": [doc("3")]},
            ],
        },
    )
    assert [b.id for b in q.answer.blanks] == ["blk_1", "blk_2"]


def test_fill_blank_ids_mismatch_rejected():
    with pytest.raises(ValidationError):
        QuestionCreate(
            content=blank_doc("blk_1", "blk_2"),
            q_type=QuestionType.FILL_IN_THE_BLANK,
            answer={
                "kind": "fill_in_the_blank",
                "blanks": [{"id": "blk_1", "accept": [doc("2")]}],
            },
        )


def test_fill_blank_accept_must_be_non_empty():
    with pytest.raises(ValidationError):
        QuestionCreate(
            content=doc("___ 是首都"),
            q_type=QuestionType.FILL_IN_THE_BLANK,
            answer={"kind": "fill_in_the_blank", "blanks": [{"id": "blk_1", "accept": []}]},
        )


def test_fill_blanks_must_be_non_empty():
    with pytest.raises(ValidationError):
        QuestionCreate(
            content=doc("题干"),
            q_type=QuestionType.FILL_IN_THE_BLANK,
            answer={"kind": "fill_in_the_blank", "blanks": []},
        )


# --------------------------------------------------------------------------- #
# legacy_unresolved 写请求必须拒绝
# --------------------------------------------------------------------------- #
def test_legacy_unresolved_rejected_on_create():
    with pytest.raises(ValidationError):
        QuestionCreate(
            content=doc("题干"),
            q_type=QuestionType.SINGLE_CHOICE,
            answer={"kind": "legacy_unresolved", "expected_kind": "single_choice", "raw": doc("A")},
        )


def test_legacy_unresolved_rejected_on_update():
    with pytest.raises(ValidationError):
        QuestionUpdate(
            answer={"kind": "legacy_unresolved", "expected_kind": "single_choice", "raw": doc("A")},
        )


# --------------------------------------------------------------------------- #
# 更新:partial,不做缺数据的误拒
# --------------------------------------------------------------------------- #
def test_update_partial_answer_only_no_false_rejection():
    upd = QuestionUpdate(answer={"kind": "single_choice", "correct": "opt_a"})
    assert upd.answer.correct == "opt_a"


def test_update_content_only():
    upd = QuestionUpdate(content=doc("新题干"))
    assert upd.content["content"][0]["content"][0]["text"] == "新题干"


def test_update_kind_mismatch_when_both_present_rejected():
    with pytest.raises(ValidationError):
        QuestionUpdate(
            q_type=QuestionType.TRUE_FALSE,
            answer={"kind": "single_choice", "correct": "opt_a"},
        )


# --------------------------------------------------------------------------- #
# ORM JSON 字符串边界:answer 传字符串也能解析
# --------------------------------------------------------------------------- #
def test_answer_json_string_is_parsed():
    q = QuestionCreate(
        content=doc("题干"),
        q_type=QuestionType.TRUE_FALSE,
        answer='{"kind": "true_false", "correct": false}',
    )
    assert q.answer.correct is False
