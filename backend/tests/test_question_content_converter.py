"""Phase 1 聚焦测试:题目内容 v1 → v2 转换器。"""

import json

from app.services.question_content_converter import (
    convert_answer,
    convert_options,
    convert_options_with_review,
    make_option_id,
    markdown_to_rich_doc,
    markdown_to_rich_doc_with_review,
    merge_legacy_answer_into_analysis,
    merge_rich_docs,
    rich_doc_to_plain_text,
)
from app.services.question_render import rich_doc_to_markdown
# --------------------------------------------------------------------------- #
def test_empty_field_returns_none():
    assert markdown_to_rich_doc(None) is None
    assert markdown_to_rich_doc("") is None
    assert markdown_to_rich_doc("   \n\t ") is None


def test_plain_paragraph():
    doc = markdown_to_rich_doc("hello world")
    assert doc == {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "hello world"}]}
        ],
    }


def test_multiple_paragraphs():
    doc = markdown_to_rich_doc("first\n\nsecond")
    assert doc is not None
    types = [n["type"] for n in doc["content"]]
    assert types == ["paragraph", "paragraph"]
    assert rich_doc_to_plain_text(doc) == "first\nsecond"


# --------------------------------------------------------------------------- #
# marks:bold / italic / sup / sub
# --------------------------------------------------------------------------- #
def test_bold_and_italic():
    doc = markdown_to_rich_doc("**b** and *i*")
    para = doc["content"][0]["content"]
    assert para[0] == {"type": "text", "text": "b", "marks": [{"type": "bold"}]}
    assert para[-1] == {"type": "text", "text": "i", "marks": [{"type": "italic"}]}


def test_nested_bold_italic():
    doc = markdown_to_rich_doc("***x***")
    node = doc["content"][0]["content"][0]
    assert node["text"] == "x"
    mark_types = {m["type"] for m in node["marks"]}
    assert mark_types == {"bold", "italic"}


def test_superscript_subscript_from_html():
    doc = markdown_to_rich_doc("x<sup>2</sup> and H<sub>2</sub>O")
    nodes = doc["content"][0]["content"]
    sup = next(n for n in nodes if n.get("text") == "2" and n.get("marks"))
    assert {"type": "superscript"} in sup["marks"]
    sub = next(
        n
        for n in nodes
        if n.get("text") == "2"
        and n.get("marks")
        and {"type": "subscript"} in n["marks"]
    )
    assert sub is not None


# --------------------------------------------------------------------------- #
# math / image
# --------------------------------------------------------------------------- #
def test_inline_math():
    doc = markdown_to_rich_doc(r"value $\sqrt2$ here")
    nodes = doc["content"][0]["content"]
    math = next(n for n in nodes if n["type"] == "inlineMath")
    assert math["attrs"]["latex"] == r"\sqrt2"


def test_block_math():
    doc = markdown_to_rich_doc("$$\n\\frac{a}{b}\n$$")
    block = doc["content"][0]
    assert block["type"] == "blockMath"
    assert block["attrs"]["latex"] == r"\frac{a}{b}"


def test_image():
    doc, needs_review = markdown_to_rich_doc_with_review("![cat](/static/media/cat.png)")
    nodes = doc["content"][0]["content"]
    img = next(n for n in nodes if n["type"] == "image")

    assert needs_review is False
    assert img["attrs"]["src"] == "/static/media/cat.png"
    assert img["attrs"]["alt"] == "cat"
    # 完全没有尺寸属性时兜底为默认宽度,不写入 needs_review。
    assert img["attrs"]["width"] == 300.0
    assert "height" not in img["attrs"]


def test_image_pandoc_dimensions_are_normalized_to_px():
    doc, needs_review = markdown_to_rich_doc_with_review(
        '![](/static/media/image6.png){width="1.5881944444444445in"\n'
        'height="1.18125in"}'
    )
    image = doc["content"][0]["content"][0]

    assert needs_review is False
    assert image == {
        "type": "image",
        "attrs": {
            "src": "/static/media/image6.png",
            "alt": "",
            "width": 152.4667,
            "height": 113.4,
        },
    }


def test_image_detached_pandoc_dimensions_are_supported():
    doc, needs_review = markdown_to_rich_doc_with_review(
        '![](/static/media/image6.png)\n'
        '{width="2.54cm" height="25.4mm"}'
    )
    nodes = doc["content"][0]["content"]

    assert needs_review is False
    assert nodes == [
        {
            "type": "image",
            "attrs": {
                "src": "/static/media/image6.png",
                "alt": "",
                "width": 96.0,
                "height": 96.0,
            },
        }
    ]


def test_invalid_image_dimension_falls_back_to_default_width():
    doc, needs_review = markdown_to_rich_doc_with_review(
        '![](/static/media/image6.png){width="50%"}'
    )
    image = doc["content"][0]["content"][0]

    # 格式非法不再写 needs_review(该字段不再由图片尺寸逻辑写入);直接兜底为默认宽度。
    assert needs_review is False
    assert image["attrs"]["width"] == 300.0
    assert "height" not in image["attrs"]


def test_image_with_only_width_keeps_height_absent():
    doc, needs_review = markdown_to_rich_doc_with_review(
        '![](/static/media/image6.png){width="1in"}'
    )
    image = doc["content"][0]["content"][0]

    assert needs_review is False
    assert image["attrs"]["width"] == 96.0
    assert "height" not in image["attrs"]


# --------------------------------------------------------------------------- #
# lists
# --------------------------------------------------------------------------- #
def test_bullet_list():
    doc = markdown_to_rich_doc("- a\n- b")
    node = doc["content"][0]
    assert node["type"] == "bulletList"
    assert len(node["content"]) == 2
    assert node["content"][0]["type"] == "listItem"
    assert rich_doc_to_plain_text(doc) == "a\nb"


def test_ordered_list():
    doc = markdown_to_rich_doc("1. a\n2. b")
    node = doc["content"][0]
    assert node["type"] == "orderedList"
    assert len(node["content"]) == 2


# --------------------------------------------------------------------------- #
# tables (pipe)
# --------------------------------------------------------------------------- #
def test_table_basic_structure():
    doc, needs_review = markdown_to_rich_doc_with_review(
        "| A | B |\n| --- | --- |\n| 1 | 2 |\n| 3 | 4 |"
    )
    table = doc["content"][0]
    assert table["type"] == "table"
    # 1 header row + 2 body rows
    assert len(table["content"]) == 3
    header_row = table["content"][0]
    assert header_row["type"] == "tableRow"
    assert [c["type"] for c in header_row["content"]] == ["tableHeader", "tableHeader"]
    body_cell = table["content"][1]["content"][0]
    assert body_cell["type"] == "tableCell"
    assert body_cell["attrs"] == {"colspan": 1, "rowspan": 1, "colwidth": None}
    # cell content is a paragraph wrapping the inline text
    assert body_cell["content"][0]["type"] == "paragraph"
    assert body_cell["content"][0]["content"][0]["text"] == "1"
    # a well-formed table must not trigger manual review
    assert needs_review is False


def test_table_preserves_inline_math_in_cell():
    doc = markdown_to_rich_doc("| x | y |\n| --- | --- |\n| $a^2$ | b |")
    cell = doc["content"][0]["content"][1]["content"][0]
    para = cell["content"][0]
    assert para["content"][0]["type"] == "inlineMath"
    assert para["content"][0]["attrs"]["latex"] == "a^2"


def test_table_empty_cell_yields_empty_paragraph():
    doc = markdown_to_rich_doc("| A | B |\n| --- | --- |\n|  | 2 |")
    empty_cell = doc["content"][0]["content"][1]["content"][0]
    assert empty_cell["type"] == "tableCell"
    assert empty_cell["content"][0]["type"] == "paragraph"
    assert "content" not in empty_cell["content"][0]


def test_table_roundtrips_back_to_markdown():
    doc = markdown_to_rich_doc("| A | B |\n| --- | --- |\n| 1 | 2 |")
    md = rich_doc_to_markdown(doc)
    assert "| A | B |" in md
    assert "| 1 | 2 |" in md


# --------------------------------------------------------------------------- #
# 降级:heading / blockquote / strike / code / codeblock / hr
# --------------------------------------------------------------------------- #
def test_heading_degraded_to_paragraph():
    doc = markdown_to_rich_doc("# Title")
    node = doc["content"][0]
    assert node["type"] == "paragraph"
    assert rich_doc_to_plain_text(doc) == "Title"


def test_blockquote_degraded():
    doc = markdown_to_rich_doc("> quoted text")
    assert all(n["type"] != "blockquote" for n in doc["content"])
    assert "quoted text" in rich_doc_to_plain_text(doc)


def test_strikethrough_preserves_text():
    doc = markdown_to_rich_doc("~~gone~~")
    assert rich_doc_to_plain_text(doc) == "gone"


def test_inline_code_degraded_preserves_text():
    doc = markdown_to_rich_doc("use `printf` here")
    assert "printf" in rich_doc_to_plain_text(doc)
    assert all(
        n["type"] != "code_inline"
        for n in doc["content"][0]["content"]
    )


def test_code_block_degraded_preserves_text():
    doc = markdown_to_rich_doc("```\nint x = 1;\n```")
    node = doc["content"][0]
    assert node["type"] == "paragraph"
    assert "int x = 1;" in rich_doc_to_plain_text(doc)


def test_horizontal_rule_drops_no_characters():
    doc = markdown_to_rich_doc("a\n\n---\n\nb")
    assert all(n["type"] != "horizontalRule" for n in doc["content"])
    assert rich_doc_to_plain_text(doc) == "a\nb"


# --------------------------------------------------------------------------- #
# 未知 / 畸形输入不丢字符
# --------------------------------------------------------------------------- #
def test_unknown_html_inline_preserved():
    doc = markdown_to_rich_doc("a<span>b</span>c")
    assert "b" in rich_doc_to_plain_text(doc)


def test_markdown_review_signal_distinguishes_supported_degradation():
    empty_doc, empty_review = markdown_to_rich_doc_with_review(None)
    heading_doc, heading_review = markdown_to_rich_doc_with_review("# Title")
    unknown_doc, unknown_review = markdown_to_rich_doc_with_review(
        "a<span>b</span>c"
    )

    assert empty_doc is None
    assert empty_review is False
    assert rich_doc_to_plain_text(heading_doc) == "Title"
    assert heading_review is False
    assert "b" in rich_doc_to_plain_text(unknown_doc)
    assert unknown_review is True


def test_result_is_json_serializable():
    doc = markdown_to_rich_doc("**b** $x$ ![a](/u.png)")
    json.dumps(doc)  # 不抛异常即可


# --------------------------------------------------------------------------- #
# options → 稳定 id
# --------------------------------------------------------------------------- #
def test_option_id_is_deterministic():
    opts = [{"label": "A", "content": "one"}, {"label": "B", "content": "two"}]
    first = convert_options(opts)
    second = convert_options(opts)
    assert [o["id"] for o in first] == [o["id"] for o in second]
    assert all(o["id"].startswith("opt_") for o in first)


def test_option_content_converted_to_rich_doc():
    opts = [{"label": "A", "content": "**bold**"}]
    result = convert_options(opts)
    assert result[0]["label"] == "A"
    assert result[0]["content"]["type"] == "doc"


def test_option_content_review_signal_is_aggregated():
    result, needs_review = convert_options_with_review(
        [
            {"label": "A", "content": "normal"},
            {"label": "B", "content": "<unknown>tag</unknown>"},
        ]
    )

    assert len(result) == 2
    assert needs_review is True


def test_make_option_id_stable():
    assert make_option_id(0, "A", "x") == make_option_id(0, "A", "x")
    assert make_option_id(0, "A", "x") != make_option_id(1, "A", "x")


# --------------------------------------------------------------------------- #
# answer 转换:五种题型
# --------------------------------------------------------------------------- #
def _choice_options():
    return convert_options(
        [
            {"label": "A", "content": "alpha"},
            {"label": "B", "content": "beta"},
            {"label": "C", "content": "gamma"},
        ]
    )


def test_single_choice_answer():
    opts = _choice_options()
    spec, needs_review = convert_answer("single_choice", "答案:A,因为选项A正确", opts)
    assert needs_review is False
    assert spec["kind"] == "single_choice"
    assert spec["correct"] == opts[0]["id"]


def test_single_choice_ambiguous_is_unresolved():
    opts = _choice_options()
    spec, needs_review = convert_answer("single_choice", "A 而不是 B", opts)
    assert spec["kind"] == "legacy_unresolved"
    assert needs_review is True
    assert spec["expected_kind"] == "single_choice"
    assert rich_doc_to_plain_text(spec["raw"]) == "A 而不是 B"


def test_multiple_choice_answer():
    opts = _choice_options()
    spec, needs_review = convert_answer("multiple_choice", "答案:A、B", opts)
    assert needs_review is False
    assert spec["kind"] == "multiple_choice"
    assert spec["correct"] == [opts[0]["id"], opts[1]["id"]]


def test_multiple_choice_unresolved():
    opts = _choice_options()
    spec, needs_review = convert_answer("multiple_choice", "见解析", opts)
    assert spec["kind"] == "legacy_unresolved"
    assert needs_review is True


def test_true_false_answer():
    for raw, expected in [("对", True), ("正确", True), ("√", True), ("错", False), ("×", False), ("F", False)]:
        spec, needs_review = convert_answer("true_false", raw)
        assert needs_review is False
        assert spec == {"kind": "true_false", "correct": expected}


def test_true_false_unresolved():
    spec, needs_review = convert_answer("true_false", "看情况")
    assert spec["kind"] == "legacy_unresolved"
    assert needs_review is True


def test_fill_in_the_blank_answer():
    raw = json.dumps([["2", "\\sqrt2"], ["3"]])
    spec, needs_review = convert_answer("fill_in_the_blank", raw)
    assert needs_review is False
    assert spec["kind"] == "fill_in_the_blank"
    assert [b["id"] for b in spec["blanks"]] == ["blk_1", "blk_2"]
    assert len(spec["blanks"][0]["accept"]) == 2
    assert spec["blanks"][0]["accept"][0]["type"] == "doc"


def test_fill_in_the_blank_accepts_native_list():
    spec, needs_review = convert_answer("fill_in_the_blank", [["a"]])
    assert spec["blanks"][0]["accept"][0]["type"] == "doc"


def test_fill_in_the_blank_malformed_is_unresolved():
    spec, needs_review = convert_answer("fill_in_the_blank", "not json")
    assert spec["kind"] == "legacy_unresolved"
    assert needs_review is True


def test_free_response_answer():
    spec, needs_review = convert_answer("free_response", "参考 **答案**")
    assert needs_review is False
    assert spec["kind"] == "free_response"
    assert spec["reference"]["type"] == "doc"


def test_free_response_propagates_markdown_review_signal():
    spec, needs_review = convert_answer(
        "free_response", "参考 <unknown>答案</unknown>"
    )

    assert spec["kind"] == "free_response"
    assert needs_review is True


def test_free_response_empty_reference_is_none():
    spec, needs_review = convert_answer("free_response", "")
    assert spec is None
    assert needs_review is False


def test_answer_spec_json_serializable():
    opts = _choice_options()
    spec, _ = convert_answer("single_choice", "A", opts)
    json.dumps(spec)


# --------------------------------------------------------------------------- #
# RichDoc 合并(legacy_unresolved 原答案并入 analysis)
# --------------------------------------------------------------------------- #
def test_merge_rich_docs_appends_without_losing_content():
    base = markdown_to_rich_doc("原有解析")
    addition = markdown_to_rich_doc("原答案文本")
    merged = merge_rich_docs(base, addition, separator="原答案:")
    text = rich_doc_to_plain_text(merged)
    assert "原有解析" in text
    assert "原答案:" in text
    assert "原答案文本" in text
    # base 的块在前,addition 的块在后(不覆盖)。
    assert text.index("原有解析") < text.index("原答案文本")


def test_merge_rich_docs_is_deterministic():
    base = markdown_to_rich_doc("a")
    addition = markdown_to_rich_doc("b")
    assert merge_rich_docs(base, addition, "S") == merge_rich_docs(base, addition, "S")


def test_merge_rich_docs_empty_sides():
    doc = markdown_to_rich_doc("only")
    assert merge_rich_docs(None, doc) == doc
    assert merge_rich_docs(doc, None) == doc
    assert merge_rich_docs(None, None) is None


def test_merge_legacy_answer_preserves_existing_analysis():
    analysis = markdown_to_rich_doc("既有解析不可丢")
    merged = merge_legacy_answer_into_analysis(analysis, "见解析")
    text = rich_doc_to_plain_text(merged)
    assert "既有解析不可丢" in text
    assert "见解析" in text


def test_merge_legacy_answer_empty_raw_returns_analysis():
    analysis = markdown_to_rich_doc("解析")
    assert merge_legacy_answer_into_analysis(analysis, "") == analysis
    assert merge_legacy_answer_into_analysis(None, "") is None
