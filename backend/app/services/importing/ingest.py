"""摄取阶段:把各种源(docx / markdown / image)归一为 CanonicalDoc。

CanonicalDoc 是抽取阶段唯一认识的输入:文本源产出 markdown,图像源产出 image_data +
公开 URL。媒体路径重写(pandoc → /static/media/...)在此一次做完,下游不再感知物理路径。
"""
from __future__ import annotations

import asyncio
import glob
import re
import shutil
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Optional
from urllib.parse import quote, unquote, urlsplit

import pypandoc

from app.core.config import settings


@dataclass
class CanonicalDoc:
    task_id: str
    markdown: str = ""                       # 文本源内容;图像源为空
    filename: Optional[str] = None           # 传给 AI 抽取的文件名上下文
    image_data: Optional[bytes] = None       # 视觉抽取用
    image_url: Optional[str] = None          # 图像源的公开访问 URL


def _ensure_task_id(task_id: Optional[str]) -> str:
    return task_id or str(uuid.uuid4())


# --- Markdown 归档(zip)摄取:解压 + 本地图片落地 + 路径重写 ---------------------

# zip 炸弹防护上限:文件数 / 解压后总字节 / 单文件字节。
_ARCHIVE_MAX_FILES = 2000
_ARCHIVE_MAX_TOTAL_BYTES = 200 * 1024 * 1024
_ARCHIVE_MAX_FILE_BYTES = 50 * 1024 * 1024

_IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".tif", ".tiff",
}

# markdown 图片语法 ![alt](URL "可选标题"):分三段捕获,只重写中间的 URL 段。
_MD_IMAGE_RE = re.compile(
    r"(!\[[^\]]*\]\()"      # 1: ![alt](
    r"([^)\s]+)"           # 2: URL(不含空格/右括号)
    r"((?:\s+\"[^\"]*\")?\))"  # 3: 可选标题 + )
)


def _safe_extract_zip(zip_path: Path, dest: Path) -> None:
    """把 zip 解压到 dest,防 zip-slip(拒绝 ../ 或绝对路径逃逸)与 zip 炸弹(数量/体积上限)。"""
    dest_root = dest.resolve()
    with zipfile.ZipFile(zip_path) as zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        if len(infos) > _ARCHIVE_MAX_FILES:
            raise ValueError(f"压缩包内文件过多(>{_ARCHIVE_MAX_FILES})")
        total = 0
        for info in infos:
            if info.file_size > _ARCHIVE_MAX_FILE_BYTES:
                raise ValueError(f"压缩包内单个文件过大: {info.filename}")
            total += info.file_size
            if total > _ARCHIVE_MAX_TOTAL_BYTES:
                raise ValueError("压缩包解压后总体积过大")
            target = (dest_root / info.filename).resolve()
            if dest_root not in target.parents and target != dest_root:
                raise ValueError(f"压缩包包含非法路径: {info.filename}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)


def _rewrite_markdown_images(
    markdown: str, *, md_dir: Path, extract_root: Path, media_dir: Path, media_id: str
) -> str:
    """把 markdown 里指向压缩包内本地图片的引用拷到媒体目录并改写成 /static/media 路径。

    仅处理能在包内解析到的本地图片;URL(http/https/data 等)、绝对路径、解析不到或逃逸出
    解压根的引用一律原样保留(坏链但保文字)。媒体按其在包内的相对路径落地,天然去重防撞名。
    """
    extract_root = extract_root.resolve()

    def _sub(match: re.Match[str]) -> str:
        raw_url = match.group(2)
        # 带 scheme(http/https/data/...)或以 / 开头的绝对路径:不动。
        if urlsplit(raw_url).scheme or raw_url.startswith("/"):
            return match.group(0)

        rel = unquote(raw_url.split("#", 1)[0].split("?", 1)[0])
        if not rel:
            return match.group(0)

        src = (md_dir / rel).resolve()
        # 逃逸出解压根、不存在、非图片扩展名:不动。
        if extract_root not in src.parents:
            return match.group(0)
        if not src.is_file() or src.suffix.lower() not in _IMAGE_EXTENSIONS:
            return match.group(0)

        rel_to_root = src.relative_to(extract_root)
        target = media_dir / rel_to_root
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)

        new_url = f"/static/media/{media_id}/{quote(rel_to_root.as_posix())}"
        return f"{match.group(1)}{new_url}{match.group(3)}"

    return _MD_IMAGE_RE.sub(_sub, markdown)


def extract_archive_and_rewrite(zip_path: Path, *, media_id: str) -> list[tuple[str, str]]:
    """解压 markdown 归档,落地被引用的本地图片,返回 [(包内 md 相对路径, 重写后 markdown)]。

    所有 md 共用同一个 media_id(同一 /static/media/{media_id}/ 目录),因此跨 md 引用同一张图
    会落到同一目标、天然去重。无 md 文件时抛 ValueError。**不做 AI 抽取**,同步/批量入口共用。
    """
    extract_root = settings.UPLOAD_DIR / media_id / "archive"
    media_dir = settings.MEDIA_DIR / media_id
    if extract_root.exists():
        shutil.rmtree(extract_root)
    extract_root.mkdir(parents=True, exist_ok=True)
    media_dir.mkdir(parents=True, exist_ok=True)

    _safe_extract_zip(zip_path, extract_root)

    md_paths = sorted(
        (p for p in extract_root.rglob("*") if p.is_file() and p.suffix.lower() == ".md"),
        key=lambda p: p.relative_to(extract_root).as_posix(),
    )
    if not md_paths:
        raise ValueError("压缩包内未找到 .md 文件")

    results: list[tuple[str, str]] = []
    for md_path in md_paths:
        content = md_path.read_text(encoding="utf-8")
        rewritten = _rewrite_markdown_images(
            content,
            md_dir=md_path.parent,
            extract_root=extract_root,
            media_dir=media_dir,
            media_id=media_id,
        )
        results.append((md_path.relative_to(extract_root).as_posix(), rewritten))
    return results


class MarkdownArchiveIngestor:
    async def ingest(
        self, zip_path: Path, *, task_id: Optional[str] = None
    ) -> CanonicalDoc:
        """同步/单条导入用:解压归档、重写图片路径,把包内所有 md 按路径序拼成一个文档。"""
        media_id = _ensure_task_id(task_id)
        parts = await asyncio.to_thread(
            extract_archive_and_rewrite, zip_path, media_id=media_id
        )
        markdown = "\n\n".join(md for _, md in parts)
        return CanonicalDoc(task_id=media_id, markdown=markdown, filename=zip_path.name)


class MarkdownIngestor:
    async def ingest(
        self, content: str, *, task_id: Optional[str] = None, filename: Optional[str] = None
    ) -> CanonicalDoc:
        task_id = _ensure_task_id(task_id)

        task_dir = settings.UPLOAD_DIR / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        output_path = task_dir / "content.md"
        await asyncio.to_thread(output_path.write_text, content, encoding="utf-8")

        return CanonicalDoc(task_id=task_id, markdown=content, filename=filename)


class DocxIngestor:
    async def ingest(self, file_path: Path, *, task_id: Optional[str] = None) -> CanonicalDoc:
        task_id = _ensure_task_id(task_id)

        task_dir = settings.UPLOAD_DIR / task_id
        media_dir = settings.MEDIA_DIR / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        media_dir.mkdir(parents=True, exist_ok=True)
        output_path = task_dir / "content.md"

        try:
            await asyncio.to_thread(
                pypandoc.convert_file,
                glob.escape(str(file_path.resolve())),
                "markdown",
                outputfile=str(output_path),
                extra_args=[f"--extract-media={str(task_dir)}", "--mathml"],
            )
        except Exception as e:
            raise RuntimeError(f"Pandoc conversion failed: {e}") from e

        if not output_path.exists():
            raise RuntimeError("Conversion output file not found")

        content = await asyncio.to_thread(output_path.read_text, encoding="utf-8")

        def handle_media_and_update_content(content_str: str) -> str:
            generated_media_folder = task_dir / "media"
            if generated_media_folder.exists():
                for item in generated_media_folder.iterdir():
                    if item.is_file():
                        shutil.move(str(item), str(media_dir / item.name))

                shutil.rmtree(str(generated_media_folder))

                pandoc_media_prefix = f"{str(task_dir)}/media/"
                public_media_url = f"/static/media/{task_id}/"
                content_str = content_str.replace(pandoc_media_prefix, public_media_url)

                output_path.write_text(content_str, encoding="utf-8")
            return content_str

        content = await asyncio.to_thread(handle_media_and_update_content, content)

        return CanonicalDoc(task_id=task_id, markdown=content, filename=file_path.name)


class ImageIngestor:
    async def ingest(self, image_file: BinaryIO, *, task_id: Optional[str] = None) -> CanonicalDoc:
        task_id = _ensure_task_id(task_id)

        media_dir = settings.MEDIA_DIR / task_id
        media_dir.mkdir(parents=True, exist_ok=True)

        image_filename = "uploaded_image.png"
        image_path = media_dir / image_filename

        image_data = await asyncio.to_thread(image_file.read)

        def save_image():
            with open(image_path, "wb") as f:
                f.write(image_data)

        await asyncio.to_thread(save_image)

        return CanonicalDoc(
            task_id=task_id,
            image_data=image_data,
            image_url=f"/static/media/{task_id}/{image_filename}",
        )
