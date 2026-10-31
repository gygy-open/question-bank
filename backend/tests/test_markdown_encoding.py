"""markdown 源文件编码回退。

以前 read_text(encoding="utf-8") 是硬编码的:GBK 存盘的 .md 会抛
UnicodeDecodeError,报错只有 "'utf-8' codec can't decode byte 0xd2 in position 3",
用户看不出这是编码问题,整个导入任务直接失败。压缩包内与单文件两条路径都受影响。
"""
import asyncio
import zipfile

import pytest

from app.services.importing.ingest import extract_markdown_archive, read_markdown_text

CHINESE = "1. 已知 $x=1$，求 $x+1$ 的值。\r\n2. 化简 $\\frac{1}{2}+\\frac{1}{3}$。\r\n"


def _write(tmp_path, name, data):
    p = tmp_path / name
    p.write_bytes(data)
    return p


def test_utf8_is_default(tmp_path):
    p = _write(tmp_path, "a.md", CHINESE.encode("utf-8"))
    text, encoding = read_markdown_text(p)
    assert text == CHINESE
    assert encoding == "utf-8-sig"


def test_utf8_bom_is_stripped(tmp_path):
    p = _write(tmp_path, "b.md", CHINESE.encode("utf-8-sig"))
    text, encoding = read_markdown_text(p)
    assert text == CHINESE
    assert not text.startswith("\ufeff")
    assert encoding == "utf-8-sig"


def test_gbk_is_decoded(tmp_path):
    p = _write(tmp_path, "c.md", CHINESE.encode("gb18030"))
    text, encoding = read_markdown_text(p)
    assert text == CHINESE
    assert encoding == "gb18030"


def test_gbk_with_bom_like_bytes_still_decodes(tmp_path):
    # GBK 里 0xd2 是"已"等字的第一个字节,旧的硬编码正是卡在这里
    p = _write(tmp_path, "d.md", "已知该方程".encode("gbk"))
    text, _ = read_markdown_text(p)
    assert text == "已知该方程"


def test_undecodable_binary_raises_with_clear_message(tmp_path):
    p = _write(tmp_path, "e.md", b"\xff\xfe\x00\x00\x81\x00\xff\xff\x80\x80")
    with pytest.raises(ValueError) as exc:
        read_markdown_text(p)
    assert "编码" in str(exc.value)


# --------------------------------------------------------------------------- #
# 归档路径:GBK 的 md 放进 zip 后同样要能读出来
# --------------------------------------------------------------------------- #
class _Store:
    def __init__(self):
        self.calls = []

    async def __call__(self, data, name):
        self.calls.append((name, len(data)))
        return "https://cdn.test/" + name


def test_archive_accepts_gbk_markdown(tmp_path):
    jpg = b"\xff\xd8\xff\xd9"
    zip_path = tmp_path / "pack.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("题目.md", CHINESE.encode("gb18030"))
        zf.writestr("images/a.jpg", jpg)

    parts = asyncio.run(extract_markdown_archive(zip_path, store=_Store()))
    assert len(parts) == 1
    rel, markdown = parts[0]
    assert rel == "题目.md"
    assert "已知" in markdown and "化简" in markdown


def test_archive_utf8_still_unchanged(tmp_path):
    jpg = b"\xff\xd8\xff\xd9"
    zip_path = tmp_path / "pack2.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("t.md", "1. 题目一 ![图](images/a.jpg)\n")
        zf.writestr("images/a.jpg", jpg)

    parts = asyncio.run(extract_markdown_archive(zip_path, store=_Store()))
    _, markdown = parts[0]
    assert "https://cdn.test/a.jpg" in markdown
