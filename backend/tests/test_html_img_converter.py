"""`<img>` 归一必须在转换器里，而不是只在导入入口。

按 #19 的结论：导入入口覆盖不到全部路径。试卷导入、AI 产出、组卷编写的 markdown
都直接进 `markdown_to_rich_doc`，不经过 `MarkdownIngestor` / `MarkdownArchiveIngestor`。
归一放在入口，这些路径里的 `<img>` 仍然会退化成一段纯文本：

    {"type": "text", "text": "<img src=\"/api/v1/media/12/content\">"}

这里的断言全部绕开导入入口，直接调转换器 —— 也就是 AI/试卷/组卷那几条路径实际走的
入口。
"""
import pytest

from app.services.question_content_converter import markdown_to_rich_doc, normalize_html_images


def _nodes(doc):
    out = []
    stack = [doc]
    while stack:
        node = stack.pop()
        out.append(node)
        stack.extend(c for c in (node.get("content") or []) if isinstance(c, dict))
    return out


def _types(doc):
    return [n.get("type") for n in _nodes(doc)]


# --------------------------------------------------------------------------- #
# 转换器直接收到 <img>（AI 产出 / 试卷导入 / 组卷编写都走这条路）
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "source",
    [
        '1. 如图 <img src="/api/v1/media/12/content"> 所示',
        "1. 如图 <img src='/api/v1/media/12/content' /> 所示",
        '1. 如图 <IMG SRC="/api/v1/media/12/content"> 所示',
    ],
)
def test_img_becomes_image_node_without_ingest(source):
    doc = markdown_to_rich_doc(source)

    assert "image" in _types(doc)
    assert "<img" not in str(doc).lower()


def test_img_keeps_asset_id():
    """转换器本来就会从 /api/v1/media/{id}/content 抽 assetId；归一不能破坏它。"""
    doc = markdown_to_rich_doc('<img src="/api/v1/media/12/content">')
    image = next(n for n in _nodes(doc) if n.get("type") == "image")

    assert image["attrs"]["assetId"] == 12
    assert image["attrs"]["src"] == "/api/v1/media/12/content"


def test_pixel_dimensions_are_preserved():
    doc = markdown_to_rich_doc('<img src="a.jpg" width="300" height="120">')
    image = next(n for n in _nodes(doc) if n.get("type") == "image")

    assert image["attrs"].get("width") == 300
    assert image["attrs"].get("height") == 120


def test_alt_text_survives():
    doc = markdown_to_rich_doc('<img src="a.jpg" alt="示意图">')
    image = next(n for n in _nodes(doc) if n.get("type") == "image")

    assert image["attrs"]["alt"] == "示意图"


def test_existing_markdown_image_untouched():
    doc = markdown_to_rich_doc("如图 ![示意图](a.jpg) 所示")
    image = next(n for n in _nodes(doc) if n.get("type") == "image")

    assert image["attrs"]["alt"] == "示意图"


def test_idempotent():
    md = '![a](a.jpg) <img src="b.jpg">'
    once = normalize_html_images(md)
    assert normalize_html_images(once) == once


@pytest.mark.parametrize(
    "source",
    ['<img alt="无地址">', '<img src="a b.jpg">'],
)
def test_unsafe_tags_left_alone(source):
    """没有 src、或 src 含空白的标签保持原样：这种 URL 无法用 markdown 图片语法表达。"""
    assert normalize_html_images(source) == source


def test_fenced_code_block_untouched():
    md = "```\n<img src=\"a.jpg\">\n```\n"
    doc = markdown_to_rich_doc(md)
    assert "<img" in str(doc).lower()
