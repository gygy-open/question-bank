"""Paper 导出编排入口:装配(格式无关)→ 按格式选渲染器 → 产出文件。

对外签名保持不变(app/api/v1/endpoints/papers.py 调用 paper_generator.generate_file)。
渲染细节在 app/services/exporting/ 各模块;此处只做参数映射与编排。
"""

from __future__ import annotations

import logging
from typing import List, Optional

from app.models.question import Question
from app.schemas.paper import ContentPosition, OutputFormat
from app.services.exporting.assemble import PaperAssembler
from app.services.exporting.contracts import ExportOptions
from app.services.exporting.registry import renderer_for

logger = logging.getLogger(__name__)


class PaperGenerator:
    def generate_file(
        self,
        title: str,
        questions: List[Question],
        format: OutputFormat,
        content_position: ContentPosition = ContentPosition.AFTER_QUESTION,
        include_answer: bool = True,
        include_analysis: bool = True,
        include_explanation: bool = True,
        include_summary: bool = True,
        include_source: bool = False,
        section_titles: Optional[List[Optional[str]]] = None,
    ) -> str:
        logger.debug(
            "Generating paper: format=%s, content_position=%s",
            format.value,
            content_position.value,
        )
        options = ExportOptions(
            title=title,
            include_answer=include_answer,
            include_analysis=include_analysis,
            include_explanation=include_explanation,
            include_summary=include_summary,
            include_source=include_source,
            details_at_end=content_position == ContentPosition.END_OF_PAPER,
            hidden_details=content_position == ContentPosition.HIDDEN,
        )
        doc = PaperAssembler(options).assemble(questions, section_titles)
        return renderer_for(format).render(doc)


paper_generator = PaperGenerator()
