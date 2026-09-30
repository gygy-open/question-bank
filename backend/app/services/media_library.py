"""媒体库读侧:学科资产列表(含引用计数)与"被引用于"明细。"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.capabilities.errors import Conflict, Forbidden
from app.core import permissions
from app.core.permissions import Permission
from app.crud.crud_question import is_question_visible
from app.models.composition import Composition, CompositionVersion, ScopeType
from app.models.media_asset import MediaAsset, MediaOwnerType, MediaPurpose, MediaReference
from app.models.question import Question, QuestionVisibility
from app.models.stimulus import Stimulus
from app.models.user import User
from app.schemas.media import (
    MediaAssetListItem,
    MediaAssetPage,
    MediaAssetUpdate,
    MediaReferenceItem,
    MediaReferences,
)
from app.services import media_service
from app.services.question_content import parse_json_field

MediaSort = Literal["newest", "oldest", "name", "size"]

_TITLE_LEN = 60


async def _editable_asset(db: AsyncSession, asset_id: int, actor: User) -> MediaAsset:
    asset = await media_service.get_readable(db, asset_id, actor)
    if asset.purpose == MediaPurpose.CONTENT.value:
        allowed = permissions.can(actor, Permission.EDIT_QUESTION, subject_id=asset.subject_id)
    else:
        allowed = actor.is_superuser or asset.owner_user_id == actor.id
    if not allowed:
        raise Forbidden("没有编辑该图片的权限")
    return asset


async def update_asset(db: AsyncSession, asset_id: int, actor: User, changes: MediaAssetUpdate) -> MediaAsset:
    asset = await _editable_asset(db, asset_id, actor)
    for name, value in changes.model_dump(exclude_unset=True).items():
        # 空字符串视为清空。
        setattr(asset, name, (value or "").strip() or None)
    await db.commit()
    await db.refresh(asset)
    return asset


async def delete_asset(db: AsyncSession, asset_id: int, actor: User) -> None:
    """软删除未被引用的资产;文件由回收任务在宽限期后清理,期间重新上传同一文件会恢复。"""
    asset = await _editable_asset(db, asset_id, actor)
    in_use = await db.scalar(
        select(func.count(MediaReference.id)).where(MediaReference.asset_id == asset.id)
    )
    if in_use:
        raise Conflict(f"图片仍被 {in_use} 处内容引用，不能删除")
    if asset.deleted_at is None:
        asset.deleted_at = datetime.utcnow()
        await db.commit()


async def list_subject_media(
    db: AsyncSession,
    subject_id: int,
    *,
    kind: Optional[str] = None,
    used: Optional[bool] = None,
    q: Optional[str] = None,
    uploader_id: Optional[int] = None,
    sort: MediaSort = "newest",
    page: int = 1,
    size: int = 30,
) -> MediaAssetPage:
    usage = (
        select(MediaReference.asset_id, func.count(MediaReference.id).label("n"))
        .group_by(MediaReference.asset_id)
        .subquery()
    )
    usage_count = func.coalesce(usage.c.n, 0)
    stmt = (
        select(MediaAsset, usage_count.label("usage_count"))
        .outerjoin(usage, usage.c.asset_id == MediaAsset.id)
        .where(
            MediaAsset.subject_id == subject_id,
            MediaAsset.purpose == MediaPurpose.CONTENT.value,
            MediaAsset.deleted_at.is_(None),
        )
    )
    if kind:
        stmt = stmt.where(MediaAsset.kind == kind)
    if used is True:
        stmt = stmt.where(usage_count > 0)
    elif used is False:
        stmt = stmt.where(usage_count == 0)
    if q:
        stmt = stmt.where(
            MediaAsset.original_filename.contains(q, autoescape=True)
            | MediaAsset.alt.contains(q, autoescape=True)
        )
    if uploader_id is not None:
        stmt = stmt.where(MediaAsset.owner_user_id == uploader_id)

    total = int(await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    order = {
        "newest": (MediaAsset.created_at.desc(), MediaAsset.id.desc()),
        "oldest": (MediaAsset.created_at.asc(), MediaAsset.id.asc()),
        "name": (MediaAsset.original_filename.asc(), MediaAsset.id.asc()),
        "size": (MediaAsset.byte_size.desc(), MediaAsset.id.desc()),
    }[sort]
    rows = await db.execute(stmt.order_by(*order).offset((page - 1) * size).limit(size))
    items = [
        MediaAssetListItem.model_validate(asset).model_copy(update={"usage_count": int(count)})
        for asset, count in rows.all()
    ]
    return MediaAssetPage(items=items, total=total, page=page, size=size)


def _text_of(node: object) -> str:
    if not isinstance(node, dict):
        return ""
    if node.get("type") == "text":
        return str(node.get("text") or "")
    return " ".join(_text_of(child) for child in node.get("content") or [])


def _snippet(raw: object, fallback: str) -> str:
    try:
        doc = parse_json_field(raw)
    except ValueError:
        doc = None
    text = " ".join(_text_of(doc).split())
    if not text:
        return fallback
    return text if len(text) <= _TITLE_LEN else f"{text[:_TITLE_LEN]}…"


def _composition_visible(comp: Composition, viewer: User) -> bool:
    if viewer.is_superuser:
        return True
    if not permissions.can(viewer, Permission.VIEW_QUESTION, subject_id=comp.subject_id):
        return False
    return comp.scope_type == ScopeType.SHARED or comp.owner_id == viewer.id


async def describe_references(db: AsyncSession, asset_id: int, viewer: User) -> MediaReferences:
    refs = (
        await db.execute(
            select(MediaReference.owner_type, MediaReference.owner_id)
            .where(MediaReference.asset_id == asset_id)
            .order_by(MediaReference.owner_type, MediaReference.owner_id)
        )
    ).all()
    ids: dict[str, list[int]] = {}
    for owner_type, owner_id in refs:
        ids.setdefault(owner_type, []).append(owner_id)

    items: list[MediaReferenceItem] = []

    question_ids = ids.get(MediaOwnerType.QUESTION.value, [])
    if question_ids:
        for question in await db.scalars(select(Question).where(Question.id.in_(question_ids))):
            if not is_question_visible(question, viewer):
                continue
            items.append(MediaReferenceItem(
                owner_type=MediaOwnerType.QUESTION.value,
                owner_id=question.id,
                title=_snippet(question.content, f"题目 #{question.id}"),
                deleted=question.deleted_at is not None,
            ))

    stimulus_ids = ids.get(MediaOwnerType.STIMULUS.value, [])
    if stimulus_ids:
        for stimulus in await db.scalars(select(Stimulus).where(Stimulus.id.in_(stimulus_ids))):
            private_hidden = (
                stimulus.visibility == QuestionVisibility.PRIVATE.value
                and not viewer.is_superuser
                and stimulus.created_by != viewer.id
            )
            if private_hidden or not permissions.can(
                viewer, Permission.VIEW_QUESTION, subject_id=stimulus.subject_id
            ):
                continue
            items.append(MediaReferenceItem(
                owner_type=MediaOwnerType.STIMULUS.value,
                owner_id=stimulus.id,
                title=_snippet(stimulus.content, f"材料 #{stimulus.id}"),
                deleted=stimulus.deleted_at is not None,
            ))

    composition_ids = ids.get(MediaOwnerType.COMPOSITION.value, [])
    if composition_ids:
        for comp in await db.scalars(select(Composition).where(Composition.id.in_(composition_ids))):
            if not _composition_visible(comp, viewer):
                continue
            items.append(MediaReferenceItem(
                owner_type=MediaOwnerType.COMPOSITION.value,
                owner_id=comp.id,
                title=comp.title,
                deleted=comp.deleted_at is not None,
                composition_id=comp.id,
                scope=comp.scope_type.value,
            ))

    version_ids = ids.get(MediaOwnerType.COMPOSITION_VERSION.value, [])
    if version_ids:
        rows = await db.execute(
            select(CompositionVersion, Composition)
            .join(Composition, Composition.id == CompositionVersion.composition_id)
            .where(CompositionVersion.id.in_(version_ids))
        )
        for version, comp in rows.all():
            if not _composition_visible(comp, viewer):
                continue
            items.append(MediaReferenceItem(
                owner_type=MediaOwnerType.COMPOSITION_VERSION.value,
                owner_id=version.id,
                title=version.title,
                deleted=comp.deleted_at is not None,
                composition_id=comp.id,
                scope=comp.scope_type.value,
                version_no=version.version_no,
            ))

    # 不可见或引用方行已不存在的,只计数不暴露 id。
    return MediaReferences(items=items, hidden_count=len(refs) - len(items))
