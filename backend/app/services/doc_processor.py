import logging
from pathlib import Path
from typing import BinaryIO, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.importing.extract import AIExtractor, ExtractionStrategy, TemplateExtractor
from app.services.importing.ingest import DocxIngestor, ImageIngestor, MarkdownArchiveIngestor, MarkdownIngestor

logger = logging.getLogger(__name__)

class DocProcessor:
    def __init__(self):
        self.client = None
        self._ai_extractor = AIExtractor()
        self._template_extractor = TemplateExtractor()
        self._docx_ingestor = DocxIngestor()
        self._markdown_ingestor = MarkdownIngestor()
        self._markdown_archive_ingestor = MarkdownArchiveIngestor()
        self._image_ingestor = ImageIngestor()

    def _extractor_for(self, method: str) -> ExtractionStrategy:
        return self._template_extractor if method == "structured" else self._ai_extractor

    async def process_markdown(self, content: str, db: AsyncSession, filename: str = None, task_id: str = None, mode: str = "extract", method: str = "ai", subject_id: Optional[int] = None) -> dict:
        """
        Process markdown content directly and extract questions.
        
        Args:
            content: Markdown text content
            db: Database session
            filename: Optional filename
            task_id: Optional task ID (if not provided, a new one will be generated)
            mode: Processing mode ("extract" or "solve")
            method: Parsing method ("ai" for AI extraction, "structured" for tag-based parsing)
        
        Returns:
            Dict with task_id, content, and extracted questions
        """
        doc = await self._markdown_ingestor.ingest(content, task_id=task_id, filename=filename)
        extracted_questions = await self._extractor_for(method).extract(
            doc.markdown, db, filename=doc.filename, mode=mode, subject_id=subject_id
        )
        return {
            "task_id": doc.task_id,
            "content": doc.markdown,
            "questions": extracted_questions,
        }

    async def process_markdown_archive(self, file_path: Path, db: AsyncSession, task_id: str = None, mode: str = "extract", method: str = "ai", subject_id: Optional[int] = None) -> dict:
        """Extract a markdown archive (zip with local images) and parse questions.

        Local image refs are rewritten to /static/media/{task_id}/... before extraction; multiple
        .md files in the archive are concatenated into one document.
        """
        doc = await self._markdown_archive_ingestor.ingest(file_path, task_id=task_id)
        extracted_questions = await self._extractor_for(method).extract(
            doc.markdown, db, filename=doc.filename, mode=mode, subject_id=subject_id
        )
        return {
            "task_id": doc.task_id,
            "content": doc.markdown,
            "questions": extracted_questions,
        }

    async def process_image(self, image_file: BinaryIO, db: AsyncSession, task_id: str = None, mode: str = "extract", subject_id: Optional[int] = None) -> dict:
        """
        Process image file and extract questions using Gemini Vision.
        
        Args:
            image_file: Image file object
            db: Database session
            task_id: Optional task ID
            mode: Processing mode ("extract" or "solve")
        
        Returns:
            Dict with task_id, image_url, and extracted questions
        """
        doc = await self._image_ingestor.ingest(image_file, task_id=task_id)
        extracted_questions = await self._ai_extractor.extract(
            "", db, image_data=doc.image_data, mode=mode, subject_id=subject_id
        )
        return {
            "task_id": doc.task_id,
            "image_url": doc.image_url,
            "questions": extracted_questions,
        }

    async def process_docx(self, file_path: Path, db: AsyncSession = None, task_id: str = None, mode: str = "extract", method: str = "ai", subject_id: Optional[int] = None) -> dict:
        """
        Convert docx to markdown, extract media, and parse questions using Gemini.
        """
        doc = await self._docx_ingestor.ingest(file_path, task_id=task_id)
        extracted_questions = await self._extractor_for(method).extract(
            doc.markdown, db, filename=doc.filename, mode=mode, subject_id=subject_id
        )
        return {
            "task_id": doc.task_id,
            "content": doc.markdown,
            "questions": extracted_questions,
        }

doc_processor = DocProcessor()
