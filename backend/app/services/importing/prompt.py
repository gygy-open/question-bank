"""抽取阶段:AI 抽取 prompt 组装。

Prompt 分层:学科覆盖(subject_prompts) → 代码默认(prompts.py),再渲染学科占位符,
最后把 tag/category 上下文注入 `{tags}` 占位符;
自定义提示词漏写该占位符时,插入到 `{content}` 之前而非追加到结尾,
保证指令仍位于素材之前。
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.crud_subject_prompt import subject_prompt as crud_subject_prompt
from app.models.subject import Subject
from app.models.tag import Tag
from app.models.tag_category import TagCategory
from app.services.prompt_utils import apply_output_language, render_subject_prompt
from app.services.prompts import get_default_prompt

logger = logging.getLogger(__name__)


class PromptBuilder:
    async def build(self, db: AsyncSession, *, mode: str, subject_id: int | None) -> str:
        """产出最终 extract/solve prompt 字符串(学科渲染 + tag 上下文注入)。"""
        prompt_key = "AI_SOLVE_PROMPT" if mode == "solve" else "AI_EXTRACT_PROMPT"

        subject = None
        override = None
        if subject_id:
            res_subj = await db.execute(select(Subject).where(Subject.id == subject_id))
            subject = res_subj.scalar_one_or_none()
            override = await crud_subject_prompt.get_value(db, subject_id, prompt_key)

        template = override if override is not None else get_default_prompt(prompt_key)
        prompt = render_subject_prompt(template, subject)

        try:
            tag_context = await self._build_tag_context(db)
            if "{tags}" in prompt:
                prompt = prompt.replace("{tags}", tag_context)
            elif "{content}" in prompt:
                # A custom prompt may omit {tags}. Appending it would put the tag
                # instructions *after* {content}, i.e. after the material they apply
                # to, so insert them in front of the content block instead.
                prompt = prompt.replace("{content}", tag_context + "\n\n{content}", 1)
                logger.warning(
                    "Prompt template has no {tags} placeholder; inserted tag context before {content}"
                )
            else:
                prompt += tag_context
                logger.warning(
                    "Prompt template has neither {tags} nor {content} placeholder; appended tag context at the end"
                )
        except Exception as e:
            logger.warning(f"Failed to fetch tag context for AI prompt: {e}")

        return apply_output_language(prompt, "solve" if mode == "solve" else "extract")

    async def _build_tag_context(self, db: AsyncSession) -> str:
        stmt_cat = (
            select(TagCategory)
            .where(TagCategory.is_active == True)  # noqa: E712
            .order_by(TagCategory.sort_order)
        )
        categories = (await db.execute(stmt_cat)).scalars().all()
        tags = (await db.execute(select(Tag))).scalars().all()

        tags_by_cat: dict[int, list[str]] = {}
        for tag in tags:
            tags_by_cat.setdefault(tag.category_id, []).append(tag.name)

        lines = []
        for cat in categories:
            cat_tags = tags_by_cat.get(cat.id, [])
            if cat_tags:
                lines.append(f"    - **{cat.name}**: {', '.join(cat_tags)}")
        return "\n".join(lines)
