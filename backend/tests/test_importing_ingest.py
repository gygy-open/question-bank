"""Phase 3 单测:Ingest 阶段(CanonicalDoc 产出、文档内图片交给 ImageStore、不留中间文件)。"""

import io
import zipfile
from pathlib import Path

import pytest

from app.core.config import settings
from app.services.importing.ingest import (
    DocxIngestor,
    ImageIngestor,
    MarkdownArchiveIngestor,
    MarkdownIngestor,
    _fix_text_wrapped_greek,
    extract_markdown_archive,
)


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    root = tmp_path / "data"
    (root / "static").mkdir(parents=True)
    monkeypatch.setattr(settings, "DATA_DIR", root)
    return root


class FakeStore:
    """记录收到的图片,按顺序发放假资产 URL;reject 中的文件名模拟入库失败。"""

    def __init__(self, reject: tuple[str, ...] = ()) -> None:
        self.received: list[tuple[str, bytes]] = []
        self.reject = reject

    async def __call__(self, data: bytes, filename: str):
        if filename in self.reject:
            return None
        self.received.append((filename, data))
        return f"/api/v1/media/{len(self.received)}/content"


def _leftovers(data_dir: Path) -> list[Path]:
    """摄取结束后 tmp/jobs、uploads、static/media 下不应残留任何文件。"""
    return [
        p
        for sub in ("tmp/jobs", "uploads", "static/media")
        if (data_dir / sub).exists()
        for p in (data_dir / sub).rglob("*")
        if p.is_file()
    ]


async def test_markdown_ingestor_returns_doc_without_writing(data_dir):
    doc = await MarkdownIngestor().ingest("# hello", task_id="md-unit", filename="q.md")

    assert doc.task_id == "md-unit"
    assert doc.markdown == "# hello"
    assert doc.filename == "q.md"
    assert _leftovers(data_dir) == []


async def test_image_ingestor_returns_bytes_without_persisting(data_dir):
    doc = await ImageIngestor().ingest(io.BytesIO(b"\x89PNG-bytes"), task_id="img-unit")

    assert doc.image_data == b"\x89PNG-bytes"
    assert _leftovers(data_dir) == []


async def test_docx_ingestor_stores_media_and_rewrites_refs(monkeypatch, tmp_path, data_dir):
    """pandoc 在 job 目录内抽取的媒体交给 store,引用改写为资产 URL,job 目录随后清理。"""
    seen = {}

    def fake_convert_file(src, to, format=None, extra_args=None, cworkdir=None):
        # 模拟 pandoc --extract-media=.:在工作目录下落 media/ 图片,返回相对引用。
        seen["format"] = format
        media = Path(cworkdir) / "media"
        media.mkdir(parents=True)
        (media / "image1.png").write_bytes(b"png")
        return '![alt](media/image1.png){width="1in"}\n![x](./media/image1.png)\n\\text{π}'

    monkeypatch.setattr(
        "app.services.importing.ingest.pypandoc.convert_file", fake_convert_file
    )

    src = tmp_path / "object-without-suffix"
    src.write_bytes(b"fake docx")
    store = FakeStore()
    doc = await DocxIngestor().ingest(src, store=store, filename="in.docx")

    assert seen["format"] == "docx"
    assert doc.filename == "in.docx"
    assert [name for name, _ in store.received] == ["image1.png", "image1.png"]
    assert doc.markdown == (
        '![alt](/api/v1/media/1/content){width="1in"}\n![x](/api/v1/media/2/content)\n\\pi'
    )
    assert _leftovers(data_dir) == []


def test_fix_text_wrapped_greek_converts_unicode_letter_to_macro():
    text = r"当$x \in \left( 0,\text{π} \right)$时"

    assert _fix_text_wrapped_greek(text) == r"当$x \in \left( 0,\pi \right)$时"


def test_fix_text_wrapped_greek_leaves_ascii_text_untouched():
    text = r"\text{sin}x - x\text{cos}x"

    assert _fix_text_wrapped_greek(text) == text


def _make_zip(tmp_path, members: dict[str, bytes]):
    zip_path = tmp_path / "archive.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return zip_path


async def test_extract_archive_stores_local_image(tmp_path, data_dir):
    zip_path = _make_zip(
        tmp_path,
        {
            "note.md": b"# Q\n\n![diagram](assets/img.png)\n",
            "sub/other.md": b"![same](../assets/img.png)\n",
            "assets/img.png": b"\x89PNG-fake",
        },
    )
    store = FakeStore()

    parts = await extract_markdown_archive(zip_path, store=store)

    assert [name for name, _ in parts] == ["note.md", "sub/other.md"]
    assert "![diagram](/api/v1/media/1/content)" in parts[0][1]
    assert "![same](/api/v1/media/2/content)" in parts[1][1]
    assert store.received == [("img.png", b"\x89PNG-fake"), ("img.png", b"\x89PNG-fake")]
    assert _leftovers(data_dir) == []


async def test_extract_archive_leaves_url_unresolved_and_rejected_refs(tmp_path):
    zip_path = _make_zip(
        tmp_path,
        {
            "note.md": (
                "![a](https://example.com/x.png)\n"
                "![b](/abs/local.png)\n"
                "![c](missing.png)\n"
                "![d](data:image/png;base64,AAAA)\n"
                "![e](bad.png)\n"
            ).encode(),
            "bad.png": b"not really",
        },
    )

    parts = await extract_markdown_archive(zip_path, store=FakeStore(reject=("bad.png",)))
    _, rewritten = parts[0]

    assert "![a](https://example.com/x.png)" in rewritten
    assert "![b](/abs/local.png)" in rewritten
    assert "![c](missing.png)" in rewritten
    assert "![d](data:image/png;base64,AAAA)" in rewritten
    assert "![e](bad.png)" in rewritten


async def test_extract_archive_rejects_zip_slip(tmp_path):
    # 手工构造带 ../ 逃逸路径的成员。
    zip_path = tmp_path / "evil.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("../evil.md", b"# pwned")

    with pytest.raises(ValueError):
        await extract_markdown_archive(zip_path, store=FakeStore())


async def test_extract_archive_without_md_raises(tmp_path):
    zip_path = _make_zip(tmp_path, {"only.png": b"png"})

    with pytest.raises(ValueError):
        await extract_markdown_archive(zip_path, store=FakeStore())


async def test_markdown_archive_ingestor_concatenates_md(tmp_path):
    zip_path = _make_zip(
        tmp_path,
        {
            "b.md": b"second",
            "a.md": b"first",
        },
    )

    doc = await MarkdownArchiveIngestor().ingest(zip_path, store=FakeStore(), task_id="arc-concat")

    assert doc.task_id == "arc-concat"
    assert doc.filename == "archive.zip"
    # 按包内路径序拼接:a.md 在 b.md 前。
    assert doc.markdown == "first\n\nsecond"

