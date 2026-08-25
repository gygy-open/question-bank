"""摄取阶段:把各种源(docx / markdown / image)归一为 CanonicalDoc。

CanonicalDoc 是抽取阶段唯一认识的输入:文本源产出 markdown,图像源产出 image_data +
公开 URL。媒体路径重写(pandoc → /static/media/...)在此一次做完,下游不再感知物理路径。
"""
from __future__ import annotations

import asyncio
import glob
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Optional

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
