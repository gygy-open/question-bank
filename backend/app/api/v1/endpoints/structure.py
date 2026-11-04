"""题干结构化 API:查看拆解、排队拆解、人工保存、审核、审核队列、同结构题、元素类型树、统计与开关。

写操作经能力层(``app/capabilities/structure.py``);读操作直接调用结构化服务,
门禁与题目读接口一致(学科查看权限 + 题目可见性)。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select

from app import capabilities, models
from app.api import deps
from app.capabilities import structure as struct_caps
from app.core.api_errors import ApiError, ErrorCode
from app.core.permissions import Permission
from app.crud.crud_question import is_question_visible, visible_questions_filter
from app.crud.crud_subject import subject as crud_subject
from app.models.question import Question
from app.models.question_structure import StructRun, StructRunState, StructTargetType
from app.models.stimulus import Stimulus
from app.services.structure import service as struct_service
from app.services.structure import settings as struct_settings
from app.services.structure import types as type_svc

router = APIRouter()

TargetTypeParam = Literal["question", "stimulus"]


class StructureSettingsUpdate(BaseModel):
    enabled: bool


class SubjectStructureSettingsUpdate(BaseModel):
    auto_decompose: bool


class DistributionRequest(BaseModel):
    question_ids: List[int] = Field(default_factory=list, max_length=2000)


class MergeRequest(BaseModel):
    target_id: int


class StructTypePatch(BaseModel):
    """类型的部分修改;请求体里出现 parent_id(含 null)表示移动。"""

    name: Optional[str] = Field(None, min_length=1, max_length=128)
    parent_id: Optional[int] = None
    definition: Optional[str] = None
    examples: Optional[List[Dict[str, Any]]] = None
    status: Optional[Literal["candidate", "active", "deprecated"]] = None
    sort_order: Optional[int] = None


# region 开关

@router.get("/settings", response_model=dict)
async def get_structure_settings(
    db: deps.SessionDep,
    subject_id: Optional[int] = None,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """总开关,以及(给定学科时)该学科的「入库自动拆解」开关与当前用户的管理权限。"""
    result: Dict[str, Any] = {
        "enabled": await struct_settings.is_enabled(db),
        "can_manage_global": bool(current_user.is_superuser),
    }
    if subject_id is not None:
        deps.require(current_user, Permission.VIEW_QUESTION, subject_id=subject_id)
        result["auto_decompose"] = await struct_settings.is_auto_decompose(db, subject_id)
        from app.core import permissions

        result["can_manage_subject"] = permissions.can(current_user, Permission.MANAGE_SUBJECT, subject_id=subject_id)
        result["can_edit_types"] = permissions.can(current_user, Permission.EDIT_TAXONOMY, subject_id=subject_id)
        result["can_edit"] = permissions.can(current_user, Permission.EDIT_QUESTION, subject_id=subject_id)
    return result


@router.put("/settings", response_model=dict)
async def update_structure_settings(
    payload: StructureSettingsUpdate,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_superuser),
) -> Any:
    """修改总开关(仅超级管理员)。"""
    await struct_settings.set_enabled(db, payload.enabled)
    return {"enabled": payload.enabled}


@router.put("/subjects/{subject_id}/settings", response_model=dict)
async def update_subject_structure_settings(
    subject_id: int,
    payload: SubjectStructureSettingsUpdate,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """修改学科的「入库自动拆解」(学科管理权限)。"""
    if await crud_subject.get(db, id=subject_id) is None:
        raise ApiError(404, ErrorCode.SUBJECT_NOT_FOUND, "Subject not found")
    deps.require(current_user, Permission.MANAGE_SUBJECT, subject_id=subject_id)
    await struct_settings.set_auto_decompose(db, subject_id, payload.auto_decompose)
    return {"auto_decompose": payload.auto_decompose}

# endregion


# region 拆解:查看与写入

@router.get("/targets/{target_type}/{target_id}", response_model=dict)
async def get_structure(
    target_type: TargetTypeParam,
    target_id: int,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """一道题(或一份材料)的结构化全貌:已采纳、待审、进行中的拆解 job。"""
    target = await _visible_target(db, target_type, target_id, current_user)
    return await struct_service.structure_view(db, target)


@router.post("/decompose", response_model=dict)
async def decompose(
    payload: struct_caps.StructureDecomposeInput,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """排队拆解(单题或批量);看不到或无权编辑的条目会被跳过。"""
    return await capabilities.run("structure.decompose", deps.api_context(db, current_user), payload)


@router.post("/save", response_model=dict)
async def save(
    payload: struct_caps.StructureSaveInput,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """保存人工修改的拆解(可选同时采纳),返回最新的结构化全貌。"""
    return await capabilities.run("structure.save", deps.api_context(db, current_user), payload)


@router.post("/review", response_model=dict)
async def review(
    payload: struct_caps.StructureReviewInput,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """采纳 / 驳回待审拆解(支持批量)。"""
    return await capabilities.run("structure.review", deps.api_context(db, current_user), payload)


@router.post("/backfill", response_model=dict)
async def backfill(
    payload: struct_caps.StructureBackfillInput,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """为学科内还没有拆解的题目排队(最低优先级,不会挡住用户的导入)。"""
    return await capabilities.run(
        "structure.backfill", deps.api_context(db, current_user, subject_id=payload.subject_id), payload
    )

# endregion


# region 审核队列

@router.get("/review-queue", response_model=dict)
async def review_queue(
    db: deps.SessionDep,
    subject_id: int,
    check: Optional[Literal["errors", "warnings", "clean"]] = None,
    origin: Optional[Literal["ai", "human"]] = None,
    target_type: Optional[TargetTypeParam] = None,
    page: int = 1,
    size: int = Query(20, ge=1, le=100),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """待审拆解列表:有体检错误的排在前面,其次是有提醒的。只列出当前用户可见的题目 / 材料。"""
    deps.require(current_user, Permission.VIEW_QUESTION, subject_id=subject_id)
    visible_questions = select(Question.id).where(
        Question.deleted_at.is_(None), visible_questions_filter(current_user)
    )
    visible_stimuli = select(Stimulus.id).where(
        Stimulus.deleted_at.is_(None), visible_questions_filter(current_user, Stimulus)
    )
    conditions = [
        StructRun.subject_id == subject_id,
        StructRun.state == StructRunState.DRAFT.value,
        or_(
            and_(StructRun.target_type == StructTargetType.QUESTION.value, StructRun.target_id.in_(visible_questions)),
            and_(StructRun.target_type == StructTargetType.STIMULUS.value, StructRun.target_id.in_(visible_stimuli)),
        ),
    ]
    if check == "errors":
        conditions.append(StructRun.check_errors > 0)
    elif check == "warnings":
        conditions.extend([StructRun.check_errors == 0, StructRun.check_warnings > 0])
    elif check == "clean":
        conditions.extend([StructRun.check_errors == 0, StructRun.check_warnings == 0])
    if origin:
        conditions.append(StructRun.origin == origin)
    if target_type:
        conditions.append(StructRun.target_type == target_type)

    total = await db.scalar(select(func.count(StructRun.id)).where(*conditions)) or 0
    runs = (
        await db.execute(
            select(StructRun)
            .where(*conditions)
            .order_by(StructRun.check_errors.desc(), StructRun.check_warnings.desc(), StructRun.id)
            .offset((max(page, 1) - 1) * size)
            .limit(size)
        )
    ).scalars().all()
    return {
        "items": [
            {
                "id": run.id,
                "target_type": run.target_type,
                "target_id": run.target_id,
                "origin": run.origin,
                "model": run.model,
                "check_errors": run.check_errors or 0,
                "check_warnings": run.check_warnings or 0,
                "preview": (run.stem_text or "")[:160],
                "created_at": run.created_at,
            }
            for run in runs
        ],
        "total": total,
        "page": page,
        "size": size,
        "pages": math.ceil(total / size) if size else 0,
    }

# endregion


# region 同结构题与统计

@router.get("/questions/{question_id}/similar", response_model=dict)
async def similar_questions(
    question_id: int,
    db: deps.SessionDep,
    limit: int = Query(10, ge=1, le=50),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """同结构题:设问类型与条件类型相近的已采纳题目(只返回可见的)。"""
    target = await _visible_target(db, StructTargetType.QUESTION.value, question_id, current_user)
    scored = await struct_service.similar_question_ids(db, target.obj, limit=limit * 3)
    if not scored:
        return {"items": []}
    rows = await db.execute(
        select(Question).where(
            Question.id.in_([item["question_id"] for item in scored]),
            Question.deleted_at.is_(None),
            visible_questions_filter(current_user),
        )
    )
    questions = {q.id: q for q in rows.scalars().all()}
    from app.services.structure.text import build_stem_text

    items = []
    for item in scored:
        question = questions.get(item["question_id"])
        if question is None:
            continue
        items.append({
            **item,
            "q_type": question.q_type,
            "preview": build_stem_text(question.content)[:160],
        })
        if len(items) >= limit:
            break
    return {"items": items}


@router.get("/stats", response_model=dict)
async def stats(
    subject_id: int,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """学科结构化进度与元素类型覆盖(首页卡片)。"""
    deps.require(current_user, Permission.VIEW_QUESTION, subject_id=subject_id)
    return await struct_service.subject_stats(db, subject_id, current_user)


@router.post("/distribution", response_model=dict)
async def distribution(
    payload: DistributionRequest,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """一组题(例如一份试卷)的元素类型分布。只统计可见的题。"""
    return await struct_service.type_distribution(db, payload.question_ids, current_user)

# endregion


# region 元素类型树

@router.get("/types", response_model=dict)
async def list_types(
    subject_id: int,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """学科的元素类型树(扁平列表,parent_id 表示层级),含被引用题数。首次访问时建好根节点。"""
    deps.require(current_user, Permission.VIEW_QUESTION, subject_id=subject_id)
    await type_svc.ensure_roots(db, subject_id)
    types = await type_svc.list_types(db, subject_id)
    usage = await type_svc.usage_counts(db, subject_id)
    return {"items": [_type_out(t, usage.get(t.id, 0)) for t in types]}


@router.get("/types/export", response_model=list)
async def export_types(
    subject_id: int,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """导出类型树(可再次导入)。"""
    deps.require(current_user, Permission.VIEW_QUESTION, subject_id=subject_id)
    return await type_svc.export_types(db, subject_id)


@router.post("/types", response_model=dict)
async def create_type(
    payload: struct_caps.StructTypeCreateInput,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    created = await capabilities.run(
        "struct_type.create", deps.api_context(db, current_user, subject_id=payload.subject_id), payload
    )
    return _type_out(created, 0)


@router.post("/types/import", response_model=dict)
async def import_types(
    payload: struct_caps.StructTypeImportInput,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    return await capabilities.run(
        "struct_type.import", deps.api_context(db, current_user, subject_id=payload.subject_id), payload
    )


@router.patch("/types/{type_id}", response_model=dict)
async def update_type(
    type_id: int,
    payload: StructTypePatch,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """修改类型;请求体里出现 ``parent_id`` 即表示移动(null 移到根)。"""
    inp = struct_caps.StructTypeUpdateInput(
        id=type_id,
        move="parent_id" in payload.model_fields_set,
        **payload.model_dump(exclude_unset=True),
    )
    updated = await capabilities.run("struct_type.update", deps.api_context(db, current_user), inp)
    usage = await type_svc.usage_counts(db, updated.subject_id)
    return _type_out(updated, usage.get(updated.id, 0))


@router.delete("/types/{type_id}", response_model=dict)
async def delete_type(
    type_id: int,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    await capabilities.run(
        "struct_type.delete", deps.api_context(db, current_user), struct_caps.StructTypeIdInput(id=type_id)
    )
    return {"ok": True}


@router.post("/types/{type_id}/merge", response_model=dict)
async def merge_type(
    type_id: int,
    payload: MergeRequest,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """把该类型合并进另一个类型(引用与子节点一并迁移)。"""
    merged = await capabilities.run(
        "struct_type.merge",
        deps.api_context(db, current_user),
        struct_caps.StructTypeMergeInput(source_id=type_id, target_id=payload.target_id),
    )
    usage = await type_svc.usage_counts(db, merged.subject_id)
    return _type_out(merged, usage.get(merged.id, 0))

# endregion


# region 内部实现

async def _visible_target(db, target_type: str, target_id: int, user: models.User) -> struct_service.Target:
    """取对象并判权:学科查看权限 + 可见性;不可见按不存在处理(与题目详情一致)。"""
    try:
        target = await struct_service.load_target(db, target_type, target_id)
    except Exception:
        raise ApiError(404, ErrorCode.STRUCTURE_TARGET_NOT_FOUND, "Not found")
    if target.subject_id is not None:
        deps.require(user, Permission.VIEW_QUESTION, subject_id=target.subject_id)
    if not is_question_visible(target.obj, user):
        raise ApiError(404, ErrorCode.STRUCTURE_TARGET_NOT_FOUND, "Not found")
    return target


def _type_out(t: Any, usage: int) -> Dict[str, Any]:
    return {
        "id": t.id,
        "subject_id": t.subject_id,
        "parent_id": t.parent_id,
        "kind": t.kind,
        "code": t.code,
        "name": t.name,
        "definition": t.definition,
        "examples": type_svc.parse_examples(t.examples),
        "status": t.status,
        "sort_order": t.sort_order,
        "usage": usage,
    }

# endregion
