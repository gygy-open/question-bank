"""替换图片:用本学科另一张图片替换旧图在所选内容中的引用。

资产不可变,替换只改写引用方内容;定稿版本是历史事实,永不改动。
"""
from __future__ import annotations

import copy
import json
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.capabilities.errors import Forbidden, Unprocessable
from app.core import permissions
from app.core.permissions import Permission
from app.crud.crud_question import is_question_visible
from app.models.composition import Composition, CompositionNode
from app.models.media_asset import MediaAsset, MediaOwnerType, MediaPurpose, MediaReference
from app.models.question import Question, QuestionVisibility
from app.models.stimulus import Stimulus
from app.models.user import User
from app.schemas.media import MediaReplaceRequest, MediaReplaceResult, MediaReplaceTarget
from app.services import media_library, media_refs, media_service
from app.services.composition_service import _add_event
from app.core.api_errors import ErrorCode

_QUESTION_FIELDS = ("content", "options", "answer", "thinking", "analysis", "summary")


def _swap(value: Any, old_id: int, new_id: int) -> tuple[Any, bool]:
    if value is None:
        return value, False
    if isinstance(value, str):
        try:
            data = json.loads(value)
        except ValueError:
            return value, False
    else:
        data = copy.deepcopy(value)
    changed = False
    for attrs in media_service.iter_media_attrs(data):
        if attrs.get("assetId") == old_id:
            attrs["assetId"] = new_id
            attrs["src"] = media_service.content_url(new_id)
            changed = True
    if not changed:
        return value, False
    return (json.dumps(data, ensure_ascii=False) if isinstance(value, str) else data), True


def _can_edit_question(question: Question, actor: User) -> bool:
    return is_question_visible(question, actor) and permissions.can(
        actor, Permission.EDIT_QUESTION, subject_id=question.subject_id
    )


def _can_edit_stimulus(stimulus: Stimulus, actor: User) -> bool:
    if (
        stimulus.visibility == QuestionVisibility.PRIVATE.value
        and not actor.is_superuser
        and stimulus.created_by != actor.id
    ):
        return False
    return permissions.can(actor, Permission.EDIT_QUESTION, subject_id=stimulus.subject_id)


def _can_edit_composition(comp: Composition, actor: User) -> bool:
    return media_library._composition_visible(comp, actor) and permissions.can(
        actor, Permission.EDIT_QUESTION, subject_id=comp.subject_id
    )


async def replace_asset(
    db: AsyncSession, asset_id: int, actor: User, request: MediaReplaceRequest
) -> MediaReplaceResult:
    old = await media_library._editable_asset(db, asset_id, actor)
    if old.purpose != MediaPurpose.CONTENT.value:
        raise Unprocessable("只有题目内容媒体可以替换", ErrorCode.MEDIA_REPLACE_CONTENT_ONLY)
    new: Optional[MediaAsset] = await db.get(MediaAsset, request.new_asset_id)
    if (
        new is None
        or new.id == old.id
        or new.deleted_at is not None
        or new.purpose != MediaPurpose.CONTENT.value
        or new.subject_id != old.subject_id
    ):
        raise Unprocessable("新文件必须是本学科媒体库中的另一个文件", ErrorCode.MEDIA_REPLACE_TARGET_INVALID)
    if new.kind != old.kind:
        raise Unprocessable("只能用同类型的文件替换(图片换图片、音频换音频)", ErrorCode.MEDIA_REPLACE_TYPE_MISMATCH)

    refs = (
        await db.execute(
            select(MediaReference.owner_type, MediaReference.owner_id).where(
                MediaReference.asset_id == old.id
            )
        )
    ).all()
    version_type = MediaOwnerType.COMPOSITION_VERSION.value
    frozen = sum(1 for owner_type, _ in refs if owner_type == version_type)
    live = {(owner_type, owner_id) for owner_type, owner_id in refs if owner_type != version_type}
    explicit = request.targets is not None
    if explicit:
        wanted = {(t.owner_type, t.owner_id) for t in request.targets}
        if wanted - live:
            raise Unprocessable("所选内容没有引用这张图片", ErrorCode.MEDIA_REPLACE_NOT_REFERENCED)
    else:
        wanted = live

    def ids(owner_type: MediaOwnerType) -> list[int]:
        return [owner_id for kind, owner_id in wanted if kind == owner_type.value]

    questions = list(await db.scalars(select(Question).where(Question.id.in_(ids(MediaOwnerType.QUESTION)))))
    stimuli = list(await db.scalars(select(Stimulus).where(Stimulus.id.in_(ids(MediaOwnerType.STIMULUS)))))
    comps = list(await db.scalars(select(Composition).where(Composition.id.in_(ids(MediaOwnerType.COMPOSITION)))))

    allowed_questions = [q for q in questions if _can_edit_question(q, actor)]
    allowed_stimuli = [s for s in stimuli if _can_edit_stimulus(s, actor)]
    allowed_comps = [c for c in comps if _can_edit_composition(c, actor)]
    skipped = len(wanted) - len(allowed_questions) - len(allowed_stimuli) - len(allowed_comps)
    if explicit and skipped:
        raise Forbidden("没有修改部分所选内容的权限", ErrorCode.MEDIA_REPLACE_FORBIDDEN_PARTIAL)

    replaced: list[MediaReplaceTarget] = []
    # 替换前后的内容版本,用于让原本已同步的稿件节点保持同步。
    question_revs: dict[int, tuple[int, int]] = {}
    stimulus_revs: dict[int, tuple[int, int]] = {}

    for question in allowed_questions:
        changed = False
        for field in _QUESTION_FIELDS:
            value, hit = _swap(getattr(question, field), old.id, new.id)
            if hit:
                setattr(question, field, value)
                changed = True
        if changed:
            before = question.content_revision or 1
            question.content_revision = before + 1
            question.updated_by = actor.id
            question_revs[question.id] = (before, before + 1)
        await media_refs.sync_question_refs(db, question)
        replaced.append(MediaReplaceTarget(owner_type="question", owner_id=question.id))

    for stimulus in allowed_stimuli:
        value, hit = _swap(stimulus.content, old.id, new.id)
        if hit:
            stimulus.content = value
            before = stimulus.content_revision or 1
            stimulus.content_revision = before + 1
            stimulus.revision = (stimulus.revision or 1) + 1
            stimulus.updated_by = actor.id
            stimulus_revs[stimulus.id] = (before, before + 1)
        await media_refs.sync_stimulus_refs(db, stimulus.id, stimulus.content, stimulus.subject_id)
        replaced.append(MediaReplaceTarget(owner_type="stimulus", owner_id=stimulus.id))

    for comp in allowed_comps:
        nodes = await db.scalars(select(CompositionNode).where(CompositionNode.composition_id == comp.id))
        changed = False
        for node in nodes:
            value, hit = _swap(node.content, old.id, new.id)
            if not hit:
                continue
            node.content = value
            changed = True
            revs = question_revs.get(node.question_id)
            if revs and node.question_revision == revs[0]:
                node.question_revision = revs[1]
            revs = stimulus_revs.get(node.stimulus_id)
            if revs and node.stimulus_revision == revs[0]:
                node.stimulus_revision = revs[1]
        if changed:
            comp.revision = (comp.revision or 1) + 1
            comp.updated_by = actor.id
            await _add_event(
                db,
                composition_id=comp.id,
                composition_revision=comp.revision,
                event_type="media_replaced",
                summary=f"替换图片 #{old.id} → #{new.id}",
                actor_id=actor.id,
                payload={"old_asset_id": old.id, "new_asset_id": new.id},
            )
        await db.flush()
        await media_refs.sync_composition_refs(db, comp.id, comp.subject_id)
        replaced.append(MediaReplaceTarget(owner_type="composition", owner_id=comp.id))

    await db.commit()
    return MediaReplaceResult(replaced=replaced, skipped=skipped, frozen=frozen)
