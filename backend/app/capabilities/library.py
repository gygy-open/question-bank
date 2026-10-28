"""知识点 / 标签域能力 —— 写路径(目前只有创建)。

鉴权与 REST 端点一致:学科作用域的 EDIT_TAXONOMY(编辑者 / 负责人 / 超管)。
读路径照旧由端点直连 CRUD。
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import crud, schemas
from app.core.api_errors import ErrorCode
from app.core.permissions import Permission
from app.models.knowledge_point import KnowledgePoint
from app.models.tag import Tag
from app.models.tag_category import TagCategory

from .base import Authz, Capability, Scope
from .context import ExecutionContext
from .errors import Invalid, NotFound
from .registry import register


async def _ensure_subject(ctx: ExecutionContext, subject_id: int) -> None:
    if not await crud.subject.get(ctx.db, id=subject_id):
        raise NotFound("Subject not found", ErrorCode.SUBJECT_NOT_FOUND)


def _required_name(value: str) -> str:
    name = (value or "").strip()
    if not name:
        raise Invalid("name must not be blank", ErrorCode.VALIDATION_FAILED)
    return name


class KnowledgePointCreateInput(BaseModel):
    subject_id: int
    name: str
    slug: Optional[str] = Field(
        default=None,
        description="Unique identifier within the subject. Generated from the name when omitted.",
    )
    parent_id: Optional[int] = Field(
        default=None,
        description="Parent knowledge point in the same subject; omit for a top-level node.",
    )


@register
class CreateKnowledgePoint(Capability[KnowledgePointCreateInput, KnowledgePoint]):
    name = "knowledge_point.create"
    description = (
        "Create a knowledge point in a subject, optionally under a parent knowledge point. "
        "Requires editor permission in the subject. Check list_knowledge_points first to avoid duplicates."
    )
    input_model = KnowledgePointCreateInput
    authz = Authz.PERMISSION
    permission = Permission.EDIT_TAXONOMY
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: KnowledgePointCreateInput) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(
        self, ctx: ExecutionContext, inp: KnowledgePointCreateInput, target: Any
    ) -> KnowledgePoint:
        name = _required_name(inp.name)
        if inp.parent_id is not None:
            parent = await crud.knowledge_point.get(ctx.db, id=inp.parent_id)
            if parent is None or parent.subject_id != inp.subject_id:
                raise NotFound("Parent knowledge point not found", ErrorCode.KNOWLEDGE_POINT_NOT_FOUND)

        slug = (inp.slug or "").strip()
        if slug:
            taken = await ctx.db.scalar(
                select(KnowledgePoint.id).where(
                    KnowledgePoint.subject_id == inp.subject_id, KnowledgePoint.slug == slug
                )
            )
            if taken is not None:
                raise Invalid(
                    "Knowledge point with this slug already exists in this subject",
                    ErrorCode.KNOWLEDGE_POINT_SLUG_EXISTS,
                )
        else:
            slug = await crud.knowledge_point.make_unique_slug(ctx.db, inp.subject_id, name)

        try:
            return await crud.knowledge_point.create(
                ctx.db,
                obj_in=schemas.KnowledgePointCreate(
                    name=name, slug=slug, parent_id=inp.parent_id, subject_id=inp.subject_id
                ),
                user_id=ctx.actor.id,
            )
        except IntegrityError:
            # 并发下撞上唯一约束
            await ctx.db.rollback()
            raise Invalid(
                "Knowledge point with this slug already exists in this subject",
                ErrorCode.KNOWLEDGE_POINT_SLUG_EXISTS,
            )


@register
class CreateTag(Capability[schemas.TagCreate, Tag]):
    name = "tag.create"
    description = (
        "Create a tag in a subject, optionally in a tag category. Tag names are unique within a subject. "
        "Requires editor permission in the subject. Check list_tags first to avoid duplicates."
    )
    input_model = schemas.TagCreate
    authz = Authz.PERMISSION
    permission = Permission.EDIT_TAXONOMY
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: schemas.TagCreate) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(self, ctx: ExecutionContext, inp: schemas.TagCreate, target: Any) -> Tag:
        name = _required_name(inp.name)
        if await crud.tag.get_by_name_in_subject(ctx.db, name=name, subject_id=inp.subject_id):
            raise Invalid("Tag with this name already exists", ErrorCode.TAG_NAME_EXISTS)
        if inp.category_id is not None:
            category = await ctx.db.get(TagCategory, inp.category_id)
            if category is None or category.subject_id != inp.subject_id:
                raise NotFound("Tag category not found", ErrorCode.TAG_CATEGORY_NOT_FOUND)
        try:
            return await crud.tag.create(
                ctx.db, obj_in=inp.model_copy(update={"name": name}), user_id=ctx.actor.id
            )
        except IntegrityError:
            await ctx.db.rollback()
            raise Invalid("Tag with this name already exists", ErrorCode.TAG_NAME_EXISTS)
