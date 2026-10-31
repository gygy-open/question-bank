"""HTML <img> 归一为 markdown 图片语法。

题库的富文本转换器只把 markdown 图片语法当成 image 节点,HTML <img> 会退化成纯文本。
实测同一张图两种写法:

    ![]( /api/v1/media/12/content )  -> {"type": "image", "attrs": {...}}
    <img src="/api/v1/media/12/content"> -> {"type": "text", "text": "<img src=...>"}

真实材料的比例:一本 698 张图的教辅,613 张写成 ![]()、85 张写成 <img>,后者全部丢失。
"""
import asyncio
import zipfile

import pytest

from app.services.importing.ingest import (
    MarkdownIngestor,
    extract_markdown_archive,
    normalize_html_images,
)

JPG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"


@pytest.mark.parametrize(
    "source,expected",
    [
        ('<img src="images/a.jpg">', "![](images/a.jpg)"),
        ("<img src='images/a.jpg' />", "![](images/a.jpg)"),
        ('<img src="images/a.jpg"/>', "![](images/a.jpg)"),
        ('<IMG SRC="images/a.jpg">', "![](images/a.jpg)"),
        ('<img alt="图" src="images/a.jpg">', "![图](images/a.jpg)"),
        ('<img src="images/a.jpg" alt="图" width="300" height="200">', "![图](images/a.jpg)"),
        ('<img data-src="x.jpg" src="images/a.jpg">', "![](images/a.jpg)"),
        ('<img title="提示" src="https://cdn.test/a.jpg">', "![](https://cdn.test/a.jpg)"),
    ],
)
def test_html_img_becomes_markdown_image(source, expected):
    assert normalize_html_images(source) == expected


def test_keeps_surrounding_text():
    md = "1. 如图 <img src='a.jpg'> 所示，求 x。"
    assert normalize_html_images(md) == "1. 如图 ![](a.jpg) 所示，求 x。"


def test_plain_markdown_image_untouched():
    md = "1. 如图 ![图](a.jpg) 所示。"
    assert normalize_html_images(md) == md


@pytest.mark.parametrize(
    "source",
    [
        '<img alt="无地址">',                 # 没有 src
        '<img src="images/a b.jpg">',         # src 含空格,无法安全表达
    ],
)
def test_unsafe_tags_left_alone(source):
    assert normalize_html_images(source) == source


def test_alt_brackets_removed():
    assert normalize_html_images('<img src="a.jpg" alt="a]b[c">') == "![abc](a.jpg)"


def test_multiple_tags_on_one_line():
    md = '<img src="1.jpg"><img src="2.jpg">'
    assert normalize_html_images(md) == "![](1.jpg)![](2.jpg)"


# --------------------------------------------------------------------------- #
# 归档路径:归一后必须真的进入图片入库
# --------------------------------------------------------------------------- #
class _Store:
    def __init__(self):
        self.names = []

    async def __call__(self, data, name):
        self.names.append(name)
        return "https://cdn.test/" + name


def test_archive_ingests_html_img(tmp_path):
    zip_path = tmp_path / "pack.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("t.md", '1. 题目一 <img src="images/a.jpg">\n')
        zf.writestr("images/a.jpg", JPG)

    store = _Store()
    parts = asyncio.run(extract_markdown_archive(zip_path, store=store))
    _, markdown = parts[0]
    assert store.names == ["a.jpg"]
    assert "https://cdn.test/a.jpg" in markdown
    assert "<img" not in markdown


def test_archive_mixed_html_and_markdown_images(tmp_path):
    zip_path = tmp_path / "pack2.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("t.md", '1. 甲 <img src="images/a.jpg"> 乙 ![图](images/b.jpg)\n')
        zf.writestr("images/a.jpg", JPG)
        zf.writestr("images/b.jpg", JPG + b"\x00")

    store = _Store()
    parts = asyncio.run(extract_markdown_archive(zip_path, store=store))
    _, markdown = parts[0]
    assert sorted(store.names) == ["a.jpg", "b.jpg"]
    assert markdown.count("https://cdn.test/") == 2


# --------------------------------------------------------------------------- #
# 单文件路径
# --------------------------------------------------------------------------- #
def test_markdown_ingestor_normalizes():
    doc = asyncio.run(MarkdownIngestor().ingest('1. 题 <img src="a.jpg">\n'))
    assert doc.markdown == "1. 题 ![](a.jpg)\n"
