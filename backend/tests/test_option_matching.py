import pytest
from pydantic import ValidationError

from app.models.question import QuestionStatus, QuestionType
from app.schemas.question import QuestionCreate, QuestionUpdate
from app.services.answer_space import DEFAULT_RULES
from app.services.exporting.answer import answer_spec_to_inline
from app.services.exporting.contracts import ExportOption
from app.services.importing.normalize import coerce_q_type
from app.services.question_legacy_adapter import LegacyQuestionError, adapt_legacy_question
from app.services.question_render import answer_spec_to_plain_text
from app.services.structured_parser import parse_structured


def doc(text: str) -> dict:
    return {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]}


def blank_doc(*blank_ids: str) -> dict:
    nodes = []
    for bid in blank_ids:
        nodes.append({"type": "text", "text": "\u2026"})
        nodes.append({"type": "blank", "attrs": {"blankId": bid}})
    return {"type": "doc", "content": [{"type": "paragraph", "content": nodes}]}


def pool(*labels: str) -> list[dict]:
    return [{"id": f"opt_{label.lower()}", "label": label, "content": doc(label)} for label in labels]


def matching(*pairs: tuple[str, str], allow_reuse: bool = False) -> dict:
    return {
        "kind": "option_matching",
        "slots": [{"id": sid, "correct": correct} for sid, correct in pairs],
        "allow_reuse": allow_reuse,
    }


def make(answer: dict, *, content: dict | None = None, options=None, status=QuestionStatus.PENDING):
    return QuestionCreate(
        content=content or blank_doc("b1", "b2"),
        q_type=QuestionType.OPTION_MATCHING,
        options=pool("A", "B", "C") if options is None else options,
        answer=answer,
        status=status,
    )


def test_valid_seven_choose_five_keeps_option_pool():
    q = make(matching(("b1", "opt_c"), ("b2", "opt_a")))
    assert [o.id for o in q.options] == ["opt_a", "opt_b", "opt_c"]
    assert [slot.correct for slot in q.answer.slots] == ["opt_c", "opt_a"]
    assert q.answer.allow_reuse is False


@pytest.mark.parametrize(
    ("answer", "message"),
    [
        (matching(("b1", "opt_a"), ("b2", "opt_a")), "\u4e92\u4e0d\u76f8\u540c"),
        (matching(("b1", "opt_a"), ("b2", "opt_z")), "\u4e0d\u5728 options"),
        (matching(("b2", "opt_a"), ("b1", "opt_b")), "\u987a\u5e8f\u4e00\u4e00\u5bf9\u5e94"),
        (matching(("b1", "opt_a"), ("b1", "opt_b")), "slot id \u5fc5\u987b\u552f\u4e00"),
        (matching(("b1", "opt_a"), ("b2", "")), "\u6bcf\u4e2a\u7a7a\u4f4d"),
    ],
)
def test_invalid_answers_rejected_for_review(answer, message):
    with pytest.raises(ValidationError, match=message):
        make(answer)


def test_reuse_allowed_when_flagged():
    q = make(matching(("b1", "opt_a"), ("b2", "opt_a"), allow_reuse=True))
    assert q.answer.allow_reuse is True


def test_draft_may_leave_slots_unanswered():
    q = make(matching(("b1", "opt_a"), ("b2", "")), status=QuestionStatus.DRAFT)
    assert q.answer.slots[1].correct == ""


def test_kind_must_match_q_type():
    with pytest.raises(ValidationError, match="\u4e0d\u4e00\u81f4"):
        QuestionCreate(
            content=doc("\u9898\u5e72"),
            q_type=QuestionType.SINGLE_CHOICE,
            options=pool("A", "B"),
            answer=matching(("b1", "opt_a")),
        )


def test_partial_update_without_options_skips_pool_check():
    update = QuestionUpdate(answer=matching(("b1", "opt_q")))
    assert update.answer.slots[0].correct == "opt_q"


def test_legacy_import_maps_letters_in_order_and_detects_reuse():
    fields = adapt_legacy_question(
        q_type="option_matching",
        content="\u9605\u8bfb\u77ed\u6587,\u4ece\u9009\u9879\u4e2d\u9009\u51fa\u80fd\u586b\u5165\u7a7a\u767d\u5904\u7684\u6700\u4f73\u9009\u9879\u3002",
        options=["A. one", "B. two", "C. three"],
        answer="C A B",
    )
    labels = {o["id"]: o["label"] for o in fields["options"]}
    assert [labels[s["correct"]] for s in fields["answer"]["slots"]] == ["C", "A", "B"]
    assert [s["id"] for s in fields["answer"]["slots"]] == ["blk_1", "blk_2", "blk_3"]
    assert fields["answer"]["allow_reuse"] is False

    reused = adapt_legacy_question(
        q_type="option_matching", content="\u5339\u914d", options=["A. x", "B. y"], answer="ABA",
    )
    assert reused["answer"]["allow_reuse"] is True


def test_legacy_import_rejects_letters_outside_pool():
    with pytest.raises(LegacyQuestionError):
        adapt_legacy_question(
            q_type="option_matching", content="\u5339\u914d", options=["A. x", "B. y"], answer="AZ",
        )


def test_structured_parser_recognizes_seven_choose_five_tag():
    q = parse_structured(
        "\u3010\u9898\u76ee\u3011\u9605\u8bfb\u4e0b\u9762\u77ed\u6587\n"
        "【题型】选项匹配\n"
        "\u3010\u9009\u9879\u3011A. one B. two C. three\n"
        "\u3010\u7b54\u6848\u3011CAB"
    ).questions[0]
    assert q["q_type"] == "option_matching"
    assert q["warnings"] == []


@pytest.mark.parametrize("raw", ["option_matching", "选项匹配", "信息匹配"])
def test_coerce_q_type(raw):
    assert coerce_q_type(raw) == QuestionType.OPTION_MATCHING


def test_answer_rendering_lists_slots_in_order():
    answer = matching(("b1", "opt_c"), ("b2", "opt_a"))
    options = pool("A", "B", "C")
    assert answer_spec_to_plain_text(answer, options) == "1. C\uff1b2. A"
    inline = answer_spec_to_inline(
        answer, [ExportOption(id=o["id"], label=o["label"], content=o["content"]) for o in options]
    )
    assert inline == [{"type": "text", "text": "1. C\uff1b2. A"}]


def test_no_answer_space_by_default():
    assert DEFAULT_RULES[QuestionType.OPTION_MATCHING.value].enabled is False
