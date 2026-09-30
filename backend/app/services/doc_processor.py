import logging
from pathlib import Path
from typing import BinaryIO, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.importing.extract import AIExtractor, ExtractionStrategy, TemplateExtractor
from app.services.importing.ingest import DocxIngestor, ImageIngestor, MarkdownArchiveIngestor, MarkdownIngestor
from app.services.importing.media import ImportImageSink

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
        extraction = await self._extractor_for(method).extract(
            doc.markdown, db, filename=doc.filename, mode=mode, subject_id=subject_id
        )
        return {
            "task_id": doc.task_id,
            "content": doc.markdown,
            "questions": extraction.questions,
            "paper": extraction.paper,
            "stimuli": extraction.stimuli,
            "question_groups": extraction.question_groups,
        }

    async def process_markdown_archive(self, file_path: Path, db: AsyncSession, task_id: str = None, mode: str = "extract", method: str = "ai", subject_id: Optional[int] = None, actor_id: Optional[int] = None, filename: Optional[str] = None) -> dict:
        """Extract a markdown archive (zip with local images) and parse questions.

        Local images become subject content assets and their refs are rewritten to asset URLs
        before extraction; multiple .md files in the archive are concatenated into one document.
        """
        sink = ImportImageSink(db, subject_id=subject_id, actor_id=actor_id)
        doc = await self._markdown_archive_ingestor.ingest(file_path, store=sink.store, task_id=task_id, filename=filename)
        extraction = await self._extractor_for(method).extract(
            doc.markdown, db, filename=doc.filename, mode=mode, subject_id=subject_id
        )
        return {
            "task_id": doc.task_id,
            "content": doc.markdown,
            "questions": extraction.questions,
            "paper": extraction.paper,
            "stimuli": extraction.stimuli,
            "question_groups": extraction.question_groups,
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
            Dict with task_id and extracted questions
        """
        doc = await self._image_ingestor.ingest(image_file, task_id=task_id)
        extraction = await self._ai_extractor.extract(
            "", db, image_data=doc.image_data, mode=mode, subject_id=subject_id
        )
        return {
            "task_id": doc.task_id,
            "questions": extraction.questions,
            "paper": extraction.paper,
            "stimuli": extraction.stimuli,
            "question_groups": extraction.question_groups,
        }

    async def process_docx(self, file_path: Path, db: AsyncSession = None, task_id: str = None, mode: str = "extract", method: str = "ai", subject_id: Optional[int] = None, actor_id: Optional[int] = None, filename: Optional[str] = None) -> dict:
        """
        Convert docx to markdown, store embedded images as assets, and parse questions.
        """
        sink = ImportImageSink(db, subject_id=subject_id, actor_id=actor_id)
        doc = await self._docx_ingestor.ingest(file_path, store=sink.store, task_id=task_id, filename=filename)
        extraction = await self._extractor_for(method).extract(
            doc.markdown, db, filename=doc.filename, mode=mode, subject_id=subject_id
        )
        return {
            "task_id": doc.task_id,
            "content": doc.markdown,
            "questions": extraction.questions,
            "paper": extraction.paper,
            "stimuli": extraction.stimuli,
            "question_groups": extraction.question_groups,
        }

doc_processor = DocProcessor()
