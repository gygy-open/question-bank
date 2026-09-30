"""维护内容 → 媒体资产的引用索引(media_references)。

每个写入路径在提交前调用 sync_refs,把该引用方当前引用的资产集合写成全量快照。
"""
from __future__ import annotations

import json
from typing import Any, Iterable, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.capabilities.errors import Unprocessable
from app.models.composition import CompositionNode
from app.models.media_asset import MediaAsset, MediaOwnerType, MediaPurpose, MediaReference
from app.services.media_service import collect_asset_ids


def _parse(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


def asset_ids_in(values: Iterable[Any]) -> set[int]:
    found: set[int] = set()
    for value in values:
        found |= collect_asset_ids(_parse(value))
    return found


async def _check_assets(db: AsyncSession, asset_ids: set[int], subject_id: Optional[int]) -> None:
    rows = await db.execute(
        select(MediaAsset.id, MediaAsset.purpose, MediaAsset.subject_id).where(
            MediaAsset.id.in_(asset_ids)
        )
    )
    valid = {
        row.id
        for row in rows
        if row.purpose == MediaPurpose.CONTENT.value and row.subject_id == subject_id
    }
    invalid = sorted(asset_ids - valid)
    if invalid:
        raise Unprocessable(f"图片不存在或不属于本学科(资产 {', '.join(map(str, invalid))})")


async def sync_refs(
    db: AsyncSession,
    owner_type: MediaOwnerType,
    owner_id: int,
    values: Iterable[Any],
    *,
    subject_id: Optional[int],
    validate: bool = True,
) -> None:
    """把引用方的引用集合同步为 values 中出现的资产;validate 时要求均为本学科内容资产。"""
    wanted = asset_ids_in(values)
    if validate and wanted:
        await _check_assets(db, wanted, subject_id)
    existing = set(
        await db.scalars(
            select(MediaReference.asset_id).where(
                MediaReference.owner_type == owner_type.value,
                MediaReference.owner_id == owner_id,
            )
        )
    )
    stale = existing - wanted
    if stale:
        await db.execute(
            delete(MediaReference).where(
                MediaReference.owner_type == owner_type.value,
                MediaReference.owner_id == owner_id,
                MediaReference.asset_id.in_(stale),
            )
        )
    db.add_all(
        MediaReference(asset_id=asset_id, owner_type=owner_type.value, owner_id=owner_id)
        for asset_id in sorted(wanted - existing)
    )
    await db.flush()


def question_values(question: Any) -> list[Any]:
    return [
        question.content,
        question.options,
        question.answer,
        question.thinking,
        question.analysis,
        question.summary,
    ]


async def sync_question_refs(db: AsyncSession, question: Any) -> None:
    await sync_refs(
        db,
        MediaOwnerType.QUESTION,
        question.id,
        question_values(question),
        subject_id=question.subject_id,
    )


async def sync_stimulus_refs(db: AsyncSession, stimulus_id: int, content: Any, subject_id: int) -> None:
    await sync_refs(db, MediaOwnerType.STIMULUS, stimulus_id, [content], subject_id=subject_id)


async def sync_composition_refs(db: AsyncSession, composition_id: int, subject_id: int) -> None:
    contents = await db.scalars(
        select(CompositionNode.content).where(CompositionNode.composition_id == composition_id)
    )
    await sync_refs(
        db, MediaOwnerType.COMPOSITION, composition_id, list(contents), subject_id=subject_id
    )


async def sync_version_refs(db: AsyncSession, version_id: int, snapshot: Any) -> None:
    # 定稿快照是不可变的历史事实:只登记引用(永不回收),不再校验。
    await sync_refs(
        db, MediaOwnerType.COMPOSITION_VERSION, version_id, [snapshot], subject_id=None, validate=False
    )
