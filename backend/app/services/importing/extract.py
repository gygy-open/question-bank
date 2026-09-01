"""抽取策略:AIExtractor(provider 配置 → prompt → 抽取 → KP 富化 → temp_id)。

产出"legacy 字符串形态"的 dict 列表(RawQuestion),喂给归一化漏斗;不产出 v2。
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.ai import AIQuestion
from app.services.ai_provider import get_ai_provider
from app.services.structured_parser import parse_structured

from .enrich import KnowledgePointEnricher
from .image_mask import mask_images, restore_images
from .prompt import PromptBuilder
from .provider_config import resolve_active_provider

logger = logging.getLogger(__name__)


class ExtractionStrategy(Protocol):
    """把归一化前的"原始内容 → RawQuestion 列表"抽象成可插拔策略。"""

    async def extract(
        self,
        content: str,
        db: AsyncSession,
        *,
        image_data: bytes | None = None,
        filename: str | None = None,
        mode: str = "extract",
        subject_id: Optional[int] = None,
    ) -> list[dict]: ...



def _assign_temp_ids(items: list[dict], parent_temp_id: Optional[str] = None) -> list[dict]:
    """给抽取结果分配临时 id 并递归处理材料题 children 的 parent_id。"""
    processed = []
    for item in items:
        if "id" not in item or not item["id"]:
            item["id"] = str(uuid.uuid4())
        if parent_temp_id:
            item["parent_id"] = parent_temp_id
        if item.get("children"):
            item["children"] = _assign_temp_ids(item["children"], item["id"])
        processed.append(item)
    return processed


class AIExtractor:
    def __init__(
        self,
        prompt_builder: Optional[PromptBuilder] = None,
        enricher: Optional[KnowledgePointEnricher] = None,
    ) -> None:
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.enricher = enricher or KnowledgePointEnricher()

    async def extract(
        self,
        content: str,
        db: AsyncSession,
        *,
        image_data: bytes | None = None,
        filename: str | None = None,
        mode: str = "extract",
        subject_id: Optional[int] = None,
    ) -> list[dict]:
        provider_name, config = await resolve_active_provider(db, is_vision=bool(image_data))
        if provider_name is None:
            logger.warning("No active AI provider configuration found.")
            return []

        config["AI_EXTRACT_PROMPT"] = await self.prompt_builder.build(
            db, mode=mode, subject_id=subject_id
        )

        provider = get_ai_provider(provider_name)

        # 视觉抽取没有 markdown 文本可遮罩;文本抽取才需要把图片 token 换成占位符再喂给 AI。
        masked_content = content
        image_map: dict[str, str] = {}
        if not image_data and content:
            masked_content, image_map = mask_images(content)

        final_content = masked_content
        if filename:
            final_content = f"文件名: {filename}\n\n{masked_content}"

        try:
            questions = await provider.extract_questions(final_content, image_data, config)
            # 文本路径无论是否遮罩到图片都跑还原,以清掉 AI 凭空写出的裸露占位符;视觉路径不涉及。
            if not image_data:
                questions = self._restore_images(questions, image_map)
            await self.enricher.enrich(
                questions, subject_id=subject_id, provider=provider, config=config
            )
            extracted = [q.model_dump() for q in questions]
            return _assign_temp_ids(extracted)
        except Exception as e:
            logger.error(f"AI Provider error: {e}")
            raise

    @staticmethod
    def _restore_images(
        questions: list[AIQuestion], image_map: dict[str, str]
    ) -> list[AIQuestion]:
        """把 AI 返回题目里的 @@IMGn@@ 占位符换回真实图片 token(容忍编号写错)，并记录异常。"""
        dumped = [q.model_dump() for q in questions]
        restored, dropped, unresolved = restore_images(dumped, image_map)
        if dropped:
            logger.warning(
                "AI extraction referenced %d more image placeholder(s) than exist; extras stripped",
                dropped,
            )
        if unresolved:
            logger.warning(
                "AI extraction result is missing %d/%d image placeholder(s)",
                unresolved, len(image_map),
            )
        return [AIQuestion(**item) for item in restored]


class TemplateExtractor:
    """确定性、无 AI 的标签模板解析(【题目】【选项】【答案】…)。忽略图像/学科。"""

    async def extract(
        self,
        content: str,
        db: AsyncSession,
        *,
        image_data: bytes | None = None,
        filename: str | None = None,
        mode: str = "extract",
        subject_id: Optional[int] = None,
    ) -> list[dict]:
        return parse_structured(content)

