"""`<br>` 应转成换行,而不是留成字面量文本。

表格单元格里没法写 markdown 换行,排版工具统一用 `<br>` 分隔多行;真实教辅里
一本 786 题的书有 316 个 `<br>`,全部在表格内。转换器已识别 `<u>`/`<sup>`/`<sub>`,
唯独没识别 `<br>`,于是它落进「无法识别的行内 HTML」分支:

    {"type": "text", "text": "<br>"}

单元格里就是一行一行的 "<br>" 字样,并且整篇被标记「需要人工复核」。
"""
import pytest

from app.services.question_content_converter import (
    markdown_to_rich_doc,
    markdown_to_rich_doc_with_review,
)


def _nodes(doc: dict) -> list[dict]:
    """按文档序遍历所有节点。"""
    out: list[dict] = []
    stack: list[dict] = [doc]
    while stack:
        node = stack.pop()
        out.append(node)
        children = [c for c in (node.get("content") or []) if isinstance(c, dict)]
        stack.extend(reversed(children))
    return out


def _types(doc: dict) -> list[str]:
    return [n.get("type", "") for n in _nodes(doc)]


def _texts(doc: dict) -> list[str]:
    return [n["text"] for n in _nodes(doc) if n.get("type") == "text"]


# "< br >" 不是合法 HTML 标签名,markdown-it 会当成纯文本,不属于本改动的范围。
@pytest.mark.parametrize("tag", ["<br>", "<br/>", "<br />", "<BR>"])
def test_br_becomes_hard_break(tag):
    doc = markdown_to_rich_doc(f"第一行{tag}第二行")

    assert "hardBreak" in _types(doc)
    assert "<br" not in str(doc).lower()


def test_br_does_not_require_review():
    doc, needs_review = markdown_to_rich_doc_with_review("甲<br>乙")

    assert needs_review is False
    assert "hardBreak" in _types(doc)


def test_text_around_br_is_preserved():
    doc = markdown_to_rich_doc("类型一 完全平方式 <br> 1. 若")
    texts = _texts(doc)

    assert "类型一 完全平方式 " in texts
    assert " 1. 若" in texts


def test_table_cell_with_br_has_no_literal_tag():
    md = (
        "| 类型 | 内容 |\n"
        "| --- | --- |\n"
        "| 类型一 <br> 1. 甲 <br> 2. 乙 | 1. 丙 <br> 2. 丁 |\n"
    )
    doc = markdown_to_rich_doc(md)

    assert "<br" not in str(doc).lower()
    assert _types(doc).count("hardBreak") == 3


def test_br_inside_inline_math_untouched():
    """$...$ 里的内容不参与 HTML 处理。"""
    doc = markdown_to_rich_doc("$a<br>b$")
    assert "hardBreak" not in _types(doc)


def test_other_unknown_html_still_flagged():
    """其它未识别的行内 HTML 仍按原样保留并标记复核 —— 本改动只针对换行标签。"""
    doc, needs_review = markdown_to_rich_doc_with_review("甲<span>乙</span>")

    assert needs_review is True


def test_existing_inline_html_still_works():
    doc = markdown_to_rich_doc("甲<sup>2</sup>乙<u>丙</u>")
    marks = [m.get("type") for n in _nodes(doc) for m in (n.get("marks") or [])]

    assert "superscript" in marks
    assert "underline" in marks
