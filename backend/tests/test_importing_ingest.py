"""Phase 3 单测:Ingest 阶段(CanonicalDoc 产出、媒体路径归一化)。"""

import io
import zipfile

import pytest

from app.core.config import settings
from app.services.importing.ingest import (
    DocxIngestor,
    ImageIngestor,
    MarkdownArchiveIngestor,
    MarkdownIngestor,
    extract_archive_and_rewrite,
)


async def test_markdown_ingestor_saves_and_returns_doc():
    doc = await MarkdownIngestor().ingest("# hello", task_id="md-unit", filename="q.md")

    assert doc.task_id == "md-unit"
    assert doc.markdown == "# hello"
    assert doc.filename == "q.md"
    saved = settings.UPLOAD_DIR / "md-unit" / "content.md"
    assert saved.read_text(encoding="utf-8") == "# hello"


async def test_image_ingestor_returns_bytes_and_public_url():
    doc = await ImageIngestor().ingest(io.BytesIO(b"\x89PNG-bytes"), task_id="img-unit")

    assert doc.image_data == b"\x89PNG-bytes"
    assert doc.image_url == "/static/media/img-unit/uploaded_image.png"
    assert (settings.MEDIA_DIR / "img-unit" / "uploaded_image.png").exists()


async def test_docx_ingestor_rewrites_media_paths(monkeypatch, tmp_path):
    """pandoc 抽取的媒体路径在摄取边界统一改写成 /static/media/<task>/。"""
    task_id = "docx-unit"
    task_dir = settings.UPLOAD_DIR / task_id

    def fake_convert_file(src, fmt, outputfile=None, extra_args=None):
        # 模拟 pandoc:写出引用 media/ 子目录图片的 markdown,并落一张媒体文件。
        media_folder = task_dir / "media"
        media_folder.mkdir(parents=True, exist_ok=True)
        (media_folder / "img1.png").write_bytes(b"png")
        content = f"![alt]({task_dir}/media/img1.png)"
        with open(outputfile, "w", encoding="utf-8") as f:
            f.write(content)

    monkeypatch.setattr(
        "app.services.importing.ingest.pypandoc.convert_file", fake_convert_file
    )

    src = tmp_path / "in.docx"
    src.write_bytes(b"fake docx")
    doc = await DocxIngestor().ingest(src, task_id=task_id)

    assert doc.filename == "in.docx"
    assert f"/static/media/{task_id}/img1.png" in doc.markdown
    # 媒体已搬到 MEDIA_DIR,临时 media/ 子目录已清理。
    assert (settings.MEDIA_DIR / task_id / "img1.png").exists()
    assert not (task_dir / "media").exists()


def _make_zip(tmp_path, members: dict[str, bytes]):
    zip_path = tmp_path / "archive.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return zip_path


def test_extract_archive_rewrites_local_image(tmp_path):
    zip_path = _make_zip(
        tmp_path,
        {
            "note.md": b"# Q\n\n![diagram](assets/img.png)\n",
            "assets/img.png": b"\x89PNG-fake",
        },
    )

    parts = extract_archive_and_rewrite(zip_path, media_id="arc-unit")

    assert len(parts) == 1
    md_name, rewritten = parts[0]
    assert md_name == "note.md"
    assert "/static/media/arc-unit/assets/img.png" in rewritten
    assert (settings.MEDIA_DIR / "arc-unit" / "assets" / "img.png").exists()


def test_extract_archive_leaves_url_and_unresolved_refs(tmp_path):
    zip_path = _make_zip(
        tmp_path,
        {
            "note.md": (
                "![a](https://example.com/x.png)\n"
                "![b](/abs/local.png)\n"
                "![c](missing.png)\n"
                "![d](data:image/png;base64,AAAA)\n"
            ).encode(),
        },
    )

    parts = extract_archive_and_rewrite(zip_path, media_id="arc-keep")
    _, rewritten = parts[0]

    assert "![a](https://example.com/x.png)" in rewritten
    assert "![b](/abs/local.png)" in rewritten
    assert "![c](missing.png)" in rewritten
    assert "![d](data:image/png;base64,AAAA)" in rewritten


def test_extract_archive_rejects_zip_slip(tmp_path):
    # 手工构造带 ../ 逃逸路径的成员。
    zip_path = tmp_path / "evil.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("../evil.md", b"# pwned")

    with pytest.raises(ValueError):
        extract_archive_and_rewrite(zip_path, media_id="arc-slip")


def test_extract_archive_without_md_raises(tmp_path):
    zip_path = _make_zip(tmp_path, {"only.png": b"png"})

    with pytest.raises(ValueError):
        extract_archive_and_rewrite(zip_path, media_id="arc-nomd")


async def test_markdown_archive_ingestor_concatenates_md(tmp_path):
    zip_path = _make_zip(
        tmp_path,
        {
            "b.md": b"second",
            "a.md": b"first",
        },
    )

    doc = await MarkdownArchiveIngestor().ingest(zip_path, task_id="arc-concat")

    assert doc.task_id == "arc-concat"
    assert doc.filename == "archive.zip"
    # 按包内路径序拼接:a.md 在 b.md 前。
    assert doc.markdown == "first\n\nsecond"

