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
from app.models.question_structure import StructElement, StructElementGroup, StructElementGroupItem, StructParam, StructRun, StructRunState, StructTargetType
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


# region 参数槽与元素组:旋钮式条件重组与原创命题


class StructParamCreate(BaseModel):
    element_id: int
    name: str = Field(..., min_length=1, max_length=64)
    value_text: str
    slot_kind: Optional[str] = None
    domain: Optional[str] = None
    replaceable: bool = True


class StructParamUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=64)
    value_text: Optional[str] = None
    slot_kind: Optional[str] = None
    domain: Optional[str] = None
    replaceable: Optional[bool] = None


class ElementGroupCreate(BaseModel):
    run_id: int
    name: str = Field(..., min_length=1, max_length=128)
    description: Optional[str] = None
    replaceable: bool = True
    sort_order: int = 0


class ElementGroupUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    description: Optional[str] = None
    replaceable: Optional[bool] = None
    sort_order: Optional[int] = None


class GroupItemLink(BaseModel):
    element_id: int


class VariantGenerate(BaseModel):
    run_id: int
    assignments: Dict[int, str] = Field(default_factory=dict)


# ---------- 参数槽 ----------

@router.get("/params", response_model=list)
async def list_struct_params(
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
    element_id: Optional[int] = None,
    replaceable_only: bool = False,
) -> Any:
    """列参数槽,可按元素/可替换性过滤。"""
    params = await struct_service.list_struct_params(
        db, element_id=element_id, replaceable_only=replaceable_only
    )
    return [
        {
            "id": p.id,
            "element_id": p.element_id,
            "name": p.name,
            "value_text": p.value_text,
            "slot_kind": p.slot_kind,
            "domain": p.domain,
            "replaceable": bool(p.replaceable),
        }
        for p in params
    ]


@router.post("/params", response_model=dict)
async def create_struct_param(
    payload: StructParamCreate,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """在元素上新建参数槽。"""
    param = await struct_service.create_struct_param(
        db,
        element_id=payload.element_id,
        name=payload.name,
        value_text=payload.value_text,
        slot_kind=payload.slot_kind,
        domain=payload.domain,
        replaceable=payload.replaceable,
    )
    return {"id": param.id}


@router.put("/params/{param_id}", response_model=dict)
async def update_struct_param(
    param_id: int,
    payload: StructParamUpdate,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """更新参数槽字段。"""
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
    param = await struct_service.update_struct_param(db, param_id, **updates)
    return {"id": param.id}


@router.delete("/params/{param_id}", response_model=dict)
async def delete_struct_param(
    param_id: int,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """删除参数槽。"""
    await struct_service.delete_struct_param(db, param_id)
    return {"ok": True}


# ---------- 元素组 ----------

@router.get("/element-groups", response_model=list)
async def list_element_groups(
    run_id: int,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """列一个拆解快照下的全部元素组。"""
    groups = await struct_service.list_element_groups(db, run_id)
    return [
        {
            "id": g.id,
            "run_id": g.run_id,
            "name": g.name,
            "description": g.description,
            "replaceable": bool(g.replaceable),
            "sort_order": g.sort_order,
        }
        for g in groups
    ]


@router.post("/element-groups", response_model=dict)
async def create_element_group(
    payload: ElementGroupCreate,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """新建元素组。"""
    group = await struct_service.create_element_group(
        db,
        run_id=payload.run_id,
        name=payload.name,
        description=payload.description,
        replaceable=payload.replaceable,
        sort_order=payload.sort_order,
    )
    return {"id": group.id}


@router.put("/element-groups/{group_id}", response_model=dict)
async def update_element_group(
    group_id: int,
    payload: ElementGroupUpdate,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """更新元素组。"""
    updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
    group = await struct_service.update_element_group(db, group_id, **updates)
    return {"id": group.id}


@router.delete("/element-groups/{group_id}", response_model=dict)
async def delete_element_group(
    group_id: int,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """删除元素组。"""
    await struct_service.delete_element_group(db, group_id)
    return {"ok": True}


@router.post("/element-groups/{group_id}/items", response_model=dict)
async def add_group_item(
    group_id: int,
    payload: GroupItemLink,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """把元素加入元素组。"""
    item = await struct_service.add_group_item(db, group_id=group_id, element_id=payload.element_id)
    return {"id": item.id}


@router.delete(
    "/element-groups/{group_id}/items/{element_id}", response_model=dict
)
async def remove_group_item(
    group_id: int,
    element_id: int,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """从元素组移出元素。"""
    await struct_service.remove_group_item(db, group_id=group_id, element_id=element_id)
    return {"ok": True}


@router.get("/element-groups/{group_id}/items", response_model=list)
async def list_group_items(
    group_id: int,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """列元素组包含的元素。"""
    elems = await struct_service.list_group_items(db, group_id)
    return [
        {
            "id": e.id,
            "run_id": e.run_id,
            "ordinal": e.ordinal,
            "content": e.content,
            "type_id": e.type_id,
            "type_hint": e.type_hint,
            "facet": e.facet,
            "span_start": e.span_start,
            "span_end": e.span_end,
        }
        for e in elems
    ]


# ---------- 变式生成 ----------

@router.get("/params/replaceable", response_model=list)
async def list_replaceable_params(
    run_id: int,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """列一个快照下全部可替换的参数槽,用于变式生成。"""
    params = await struct_service.list_replaceable_params(db, run_id)
    return [
        {
            "id": p.id,
            "element_id": p.element_id,
            "name": p.name,
            "value_text": p.value_text,
            "slot_kind": p.slot_kind,
            "domain": p.domain,
        }
        for p in params
    ]


@router.post("/variants", response_model=dict)
async def generate_variant(
    payload: VariantGenerate,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """把参数槽新值应用到题干快照,生成变式题干文本(不写库)。"""
    run = await struct_service.get_run(db, payload.run_id)
    params = await struct_service.list_replaceable_params(db, payload.run_id)
    params_by_id = {p.id: p for p in params}
    new_stem = struct_service.apply_param_values_to_stem(run.stem_text, payload.assignments, params_by_id)
    return {"run_id": payload.run_id, "new_stem_text": new_stem}


# region 同源检索与跨题拼装:题目多样化玩法


class ComposeRequest(BaseModel):
    element_ids: List[int] = Field(..., description="元素 id 列表,按期望顺序排列")
    separator: str = Field("\n", description="元素间分隔符")


# ---------- 同源检索:按元素组 ----------

@router.get("/similar/element-group", response_model=list)
async def similar_by_element_group(
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
    run_id: int = Query(..., description="拆解快照 id"),
    limit: int = Query(20, ge=1, le=100, description="返回上限"),
) -> Any:
    """按元素组成员查找同源题:找拥有相同元素的其他题。"""
    results = await struct_service.find_similar_by_element_group(db, run_id, limit=limit)
    return results


# ---------- 同源检索:按参数槽 ----------

@router.get("/similar/param", response_model=list)
async def similar_by_param(
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
    param_name: str = Query(..., description="参数槽名"),
    param_value: str = Query(..., description="参数槽值"),
    limit: int = Query(20, ge=1, le=100, description="返回上限"),
) -> Any:
    """按参数槽名/值查找同源题:找有相同参数槽的其他题。"""
    results = await struct_service.find_similar_by_param(
        db, param_name=param_name, param_value=param_value, limit=limit
    )
    return results


# ---------- 跨题拼装 ----------

@router.post("/compose", response_model=dict)
async def compose_stem(
    payload: ComposeRequest,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """跨题拼装题干:按给定元素 id 顺序拼接成新题干文本(不写库)。"""
    stem = await struct_service.compose_stem(
        db, element_ids=payload.element_ids, separator=payload.separator
    )
    return {"stem_text": stem, "element_count": len(payload.element_ids)}


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
