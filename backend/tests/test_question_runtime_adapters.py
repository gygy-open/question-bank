"""Phase 4 聚焦测试:后端 v2 运行时适配(legacy adapter / 渲染 / Paper 导出)。"""

import json
import types

import pytest
from types import SimpleNamespace

from app.services.question_content import (
    to_db_json,
    validate_question_for_exam,
    validate_rich_doc,
)
from app.services.question_content_v1 import (
    convert_answer,
    convert_options,
    markdown_to_rich_doc,
)
from app.services.question_legacy_adapter import (
    LegacyQuestionError,
    adapt_legacy_question,
)
from app.services.question_render import (
    answer_spec_to_markdown,
    answer_spec_to_plain_text,
    rich_doc_to_markdown,
    rich_doc_to_plain_text,
)
from app.services import paper_generator as pg_module
from app.services.paper_generator import PaperGenerator


# --------------------------------------------------------------------------- #
# 1. legacy adapter:五题型成功
# --------------------------------------------------------------------------- #
def test_adapter_single_choice_list_options():
    v2 = adapt_legacy_question(
        q_type="single_choice",
        content="下列哪个正确?",
        options=["红色", "绿色", "蓝色"],
        answer="A",
    )
    assert v2["content"]["type"] == "doc"
    assert [o["label"] for o in v2["options"]] == ["A", "B", "C"]
    assert v2["answer"]["kind"] == "single_choice"
    assert v2["answer"]["correct"] == v2["options"][0]["id"]


def test_adapter_single_choice_labeled_option_strings():
    v2 = adapt_legacy_question(
        q_type="single_choice",
        content="题干",
        options=["A. 甲", "B. 乙", "C. 丙"],
        answer="答案:B",
    )
    assert v2["answer"]["correct"] == v2["options"][1]["id"]


def test_adapter_multiple_choice():
    v2 = adapt_legacy_question(
        q_type="multiple_choice",
        content="多选",
        options=[{"label": "A", "content": "甲"}, {"label": "B", "content": "乙"}, {"label": "C", "content": "丙"}],
        answer="答案:A、C",
    )
    assert v2["answer"]["kind"] == "multiple_choice"
    assert v2["answer"]["correct"] == [v2["options"][0]["id"], v2["options"][2]["id"]]


def test_adapter_true_false():
    v2 = adapt_legacy_question(q_type="true_false", content="判断", answer="对")
    assert v2["answer"] == {"kind": "true_false", "correct": True}
    assert v2["options"] is None


def test_adapter_fill_in_the_blank_json_answer():
    v2 = adapt_legacy_question(
        q_type="fill_in_the_blank",
        content="1+1=___",
        answer=json.dumps([["2"]]),
    )
    assert v2["answer"]["kind"] == "fill_in_the_blank"
    assert v2["answer"]["blanks"][0]["accept"][0]["type"] == "doc"


def test_adapter_free_response_reference_and_optional():
    v2 = adapt_legacy_question(q_type="free_response", content="解答", answer="参考 **答案**")
    assert v2["answer"]["kind"] == "free_response"
    assert v2["answer"]["reference"]["type"] == "doc"

    v2_none = adapt_legacy_question(q_type="free_response", status="draft", content="解答")
    assert v2_none["answer"] is None


def test_adapter_converts_richtext_fields():
    v2 = adapt_legacy_question(
        q_type="free_response",
        status="draft",
        content="题干 $x^2$",
        thinking="**思路**",
        analysis="解析",
        summary="总结",
    )
    assert rich_doc_to_plain_text(v2["thinking"]) == "思路"
    assert v2["analysis"]["type"] == "doc"
    assert v2["summary"]["type"] == "doc"


# --------------------------------------------------------------------------- #
# 2. unresolved 拒绝:不静默持久化 legacy_unresolved
# --------------------------------------------------------------------------- #
def test_adapter_rejects_unresolved_single_choice():
    with pytest.raises(LegacyQuestionError):
        adapt_legacy_question(
            q_type="single_choice",
            content="题干",
            options=["甲", "乙"],
            answer="见解析",
        )


def test_adapter_rejects_unresolved_true_false():
    with pytest.raises(LegacyQuestionError):
        adapt_legacy_question(q_type="true_false", content="题干", answer="看情况")


def test_adapter_rejects_empty_content():
    with pytest.raises(LegacyQuestionError):
        adapt_legacy_question(q_type="free_response", content="   ")


def test_adapter_rejects_empty_answer_for_pending():
    with pytest.raises(LegacyQuestionError):
        adapt_legacy_question(q_type="free_response", status="pending", content="题干")


def test_exam_validation_rejects_incomplete_draft():
    question = SimpleNamespace(
        q_type="free_response",
        content=to_db_json(markdown_to_rich_doc("题干")),
        options=None,
        answer=None,
    )
    with pytest.raises(ValueError, match="answer is required"):
        validate_question_for_exam(question)


# --------------------------------------------------------------------------- #
# 3. 明确答案解析:不被 "because" 等英文单词污染
# --------------------------------------------------------------------------- #
def _opts():
    return convert_options(
        [{"label": "A", "content": "a"}, {"label": "B", "content": "b"}, {"label": "C", "content": "c"}]
    )


def test_because_does_not_pollute_letter_extraction():
    spec, needs_review = convert_answer("single_choice", "because it is right", _opts())
    assert spec["kind"] == "legacy_unresolved"
    assert needs_review is True


def test_explicit_prefixed_answer_ignores_explanation_letters():
    # 前缀明确,只取开头字母,不扫描 "选项A" / "because" 里的字母。
    spec, needs_review = convert_answer(
        "single_choice", "答案:A,因为 because 选项 A 正确", _opts()
    )
    assert needs_review is False
    assert spec["correct"] == _opts()[0]["id"]


def test_plain_letter_and_list_formats():
    opts = _opts()
    assert convert_answer("single_choice", "A", opts)[0]["correct"] == opts[0]["id"]
    spec, _ = convert_answer("multiple_choice", "A、B、C", opts)
    assert spec["correct"] == [opts[0]["id"], opts[1]["id"], opts[2]["id"]]
    spec2, _ = convert_answer("multiple_choice", "ABC", opts)
    assert spec2["correct"] == [opts[0]["id"], opts[1]["id"], opts[2]["id"]]


# --------------------------------------------------------------------------- #
# 4. RichDoc plain / markdown 渲染
# --------------------------------------------------------------------------- #
def test_rich_doc_to_markdown_marks_and_math():
    doc = markdown_to_rich_doc("**b** and *i* with $x^2$")
    md = rich_doc_to_markdown(doc)
    assert "**b**" in md
    assert "*i*" in md
    assert "$x^2$" in md


def test_rich_doc_to_markdown_block_math_image_list():
    doc = markdown_to_rich_doc("- a\n- b")
    assert "- a" in rich_doc_to_markdown(doc)

    img = markdown_to_rich_doc("![cat](/static/media/cat.png)")
    assert "![cat](/static/media/cat.png)" in rich_doc_to_markdown(img)

    sized_img = {
        "type": "doc",
        "content": [
            {
                "type": "image",
                "attrs": {
                    "src": "/static/media/cat.png",
                    "alt": "cat",
                    "width": 152.4667,
                    "height": 113.4,
                },
            }
        ],
    }
    assert rich_doc_to_markdown(sized_img) == (
        '![cat](/static/media/cat.png){width="1.5882in" height="1.1813in"}'
    )

    block = markdown_to_rich_doc("$$\n\\frac{a}{b}\n$$")
    md = rich_doc_to_markdown(block)
    assert md.startswith("$$") and "\\frac{a}{b}" in md


def test_rich_doc_to_markdown_accepts_json_string():
    doc = markdown_to_rich_doc("hello")
    assert rich_doc_to_markdown(to_db_json(doc)) == "hello"


def test_rich_doc_image_dimensions_must_be_valid_px_numbers():
    valid = {
        "type": "doc",
        "content": [
            {
                "type": "image",
                "attrs": {"src": "/image.png", "width": 320.5, "height": 180},
            }
        ],
    }
    assert validate_rich_doc(valid) is valid

    for invalid in ("320px", 0, -1, float("inf"), 20_001, True):
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "image",
                    "attrs": {"src": "/image.png", "width": invalid},
                }
            ],
        }
        with pytest.raises(ValueError, match="image width"):
            validate_rich_doc(doc)


def test_rich_doc_to_markdown_unknown_node_does_not_crash():
    doc = {
        "type": "doc",
        "content": [
            {"type": "table", "content": [
                {"type": "tableRow", "content": [
                    {"type": "tableCell", "content": [markdown_to_rich_doc("h1")]},
                    {"type": "tableCell", "content": [markdown_to_rich_doc("h2")]},
                ]},
            ]},
            {"type": "futureNode", "attrs": {}, "content": [{"type": "text", "text": "keep"}]},
        ],
    }
    md = rich_doc_to_markdown(doc)
    assert "h1" in md and "h2" in md
    assert "keep" in md


# --------------------------------------------------------------------------- #
# 5. answer formatter
# --------------------------------------------------------------------------- #
def test_answer_formatter_choice_shows_label():
    opts = _opts()
    answer = {"kind": "single_choice", "correct": opts[1]["id"]}
    assert answer_spec_to_plain_text(answer, opts) == "B"
    assert answer_spec_to_markdown(answer, opts) == "B"

    multi = {"kind": "multiple_choice", "correct": [opts[0]["id"], opts[2]["id"]]}
    assert answer_spec_to_plain_text(multi, opts) == "A，C"


def test_answer_formatter_true_false():
    assert answer_spec_to_plain_text({"kind": "true_false", "correct": True}) == "对"
    assert answer_spec_to_plain_text({"kind": "true_false", "correct": False}) == "错"


def test_answer_formatter_fill_joins_accept():
    answer = {
        "kind": "fill_in_the_blank",
        "blanks": [
            {"id": "blk_1", "accept": [markdown_to_rich_doc("2"), markdown_to_rich_doc("二")]},
            {"id": "blk_2", "accept": [markdown_to_rich_doc("3")]},
        ],
    }
    assert answer_spec_to_plain_text(answer) == "2 或 二；3"


def test_answer_formatter_free_and_legacy():
    free = {"kind": "free_response", "reference": markdown_to_rich_doc("参考 **答案**")}
    assert "参考" in answer_spec_to_markdown(free)
    legacy = {"kind": "legacy_unresolved", "expected_kind": "single_choice", "raw": markdown_to_rich_doc("原始答案")}
    assert answer_spec_to_plain_text(legacy) == "原始答案"


def test_answer_formatter_accepts_json_string():
    answer_json = to_db_json({"kind": "true_false", "correct": True})
    assert answer_spec_to_plain_text(answer_json) == "对"


# --------------------------------------------------------------------------- #
# 6. Paper 导出最小路径(Markdown / LaTeX,mock pypandoc)
# --------------------------------------------------------------------------- #
def _make_question(**overrides):
    q = types.SimpleNamespace(
        id=1,
        q_type="single_choice",
        difficulty=1,
        content=to_db_json(markdown_to_rich_doc("题干 $x^2$")),
        options=[
            {"id": "opt_a", "label": "A", "content": markdown_to_rich_doc("**甲**")},
            {"id": "opt_b", "label": "B", "content": markdown_to_rich_doc("乙")},
        ],
        answer=to_db_json({"kind": "single_choice", "correct": "opt_b"}),
        thinking=to_db_json(markdown_to_rich_doc("思路")),
        analysis=to_db_json(markdown_to_rich_doc("解析")),
        summary=None,
        source=None,
    )
    for k, v in overrides.items():
        setattr(q, k, v)
    return q


def test_paper_generate_markdown_renders_v2():
    gen = PaperGenerator()
    q = _make_question()
    md = gen.generate_markdown("卷子", [q])
    # 题干/选项/答案均已渲染,且没有 JSON 原文泄漏。
    assert "题干 $x^2$" in md
    assert "**甲**" in md
    assert "**【答案】** B" in md
    assert '"type": "doc"' not in md
    assert '{"kind"' not in md


def test_paper_generate_markdown_fill_answer():
    gen = PaperGenerator()
    answer = {
        "kind": "fill_in_the_blank",
        "blanks": [{"id": "blk_1", "accept": [markdown_to_rich_doc("42")]}],
    }
    q = _make_question(
        q_type="fill_in_the_blank",
        options=None,
        content=to_db_json(markdown_to_rich_doc("答案是___")),
        answer=to_db_json(answer),
    )
    md = gen.generate_markdown("卷子", [q])
    assert "**【答案】** 42" in md


def test_paper_generate_latex_uses_markdown_not_json(monkeypatch):
    captured = []

    def fake_convert(text, to, format=None, outputfile=None, extra_args=None):
        captured.append(text)
        return "TEX"

    monkeypatch.setattr(pg_module.pypandoc, "convert_text", fake_convert)
    gen = PaperGenerator()
    q = _make_question()
    result = gen.generate_latex_via_jinja("卷子", [q])
    assert isinstance(result, str)
    # 送进 pypandoc 的必须是渲染后的 Markdown,而非 JSON 原文。
    assert captured, "pypandoc should have been called"
    for text in captured:
        assert '"type": "doc"' not in text
        assert '{"kind"' not in text
    joined = "\n".join(captured)
    assert "题干 $x^2$" in joined
