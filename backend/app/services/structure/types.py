"""元素类型树:按学科维护的条件 / 设问分类。

类型由老师维护(新建、改名、移动、合并、停用、导入导出),也可以由二期的「归纳」
产生候选。只有 active 的类型会提供给 AI、出现在筛选里。

每个学科首次使用时自动建好根节点:
- 数学:条件按领域分三棵子树——代数(式的结构)、几何(形的结构)、统计(统计量的结构),
  这是老师反馈中给出的第一层划分;
- 其他学科:一个「条件」根;
- 所有学科:一个「设问」根。
根节点之下的具体类型不预置,由老师导入或从拆解结果中归纳。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.capabilities.errors import Conflict, Invalid, NotFound
from app.core.api_errors import ErrorCode
from app.models.question_structure import (
    StructAsk,
    StructElement,
    StructRun,
    StructRunState,
    StructType,
    StructTypeKind,
    StructTypeKnowledgePoint,
    StructTypeStatus,
)
from app.models.subject import Subject

# 数学学科的识别:slug 或名称里出现这些词。
_MATH_HINTS = ("math", "数学")


@dataclass(frozen=True)
class _RootSpec:
    code: str
    kind: StructTypeKind
    name: str
    definition: str


_MATH_ROOTS = (
    _RootSpec("algebra", StructTypeKind.CONDITION, "代数", "式的结构:函数式、方程、不等式、数列等代数对象及其关系。"),
    _RootSpec("geometry", StructTypeKind.CONDITION, "几何", "形的结构:图形、位置关系、度量与图形变换。"),
    _RootSpec("statistics", StructTypeKind.CONDITION, "统计", "统计量的结构:样本、统计图表、概率模型与统计量。"),
)
_GENERIC_CONDITION_ROOT = _RootSpec("condition", StructTypeKind.CONDITION, "条件", "题干给出的已知条件与研究对象。")
_ASK_ROOT = _RootSpec("ask", StructTypeKind.ASK, "设问", "题目要求回答的问题。")
_METHOD_ROOT = _RootSpec("method", StructTypeKind.METHOD, "方法", "解题步骤用到的方法与思维动作;权重用于计算思维量难度。")


# region 查询

async def ensure_roots(db: AsyncSession, subject_id: int) -> None:
    """学科还没有任何类型时建好根节点;已有类型但缺方法根时补建方法根。

    幂等;并发重复插入由唯一约束兜底。会提交。
    """
    kinds = set((await db.execute(
        select(StructType.kind).where(StructType.subject_id == subject_id).distinct()
    )).scalars().all())
    if kinds:
        # 一期建好的学科没有方法根:补建(老师删掉的其他根不会被重新建出来)。
        if StructTypeKind.METHOD.value in kinds:
            return
        specs: tuple = (_METHOD_ROOT,)
        base_order = 100
    else:
        subject = await db.get(Subject, subject_id)
        if subject is None:
            return
        specs = (*(_MATH_ROOTS if _is_math(subject) else (_GENERIC_CONDITION_ROOT,)), _ASK_ROOT, _METHOD_ROOT)
        base_order = 0
    for order, spec in enumerate(specs, start=base_order):
        db.add(StructType(
            subject_id=subject_id,
            parent_id=None,
            kind=spec.kind.value,
            code=spec.code,
            name=spec.name,
            definition=spec.definition,
            status=StructTypeStatus.ACTIVE.value,
            sort_order=order,
        ))
    try:
        await db.commit()
    except IntegrityError:
        # 另一个请求同时建好了根节点。
        await db.rollback()


async def list_types(
    db: AsyncSession, subject_id: int, *, statuses: Optional[Sequence[str]] = None
) -> List[StructType]:
    """学科的全部类型(按排序号、id),可按状态过滤。"""
    stmt = select(StructType).where(StructType.subject_id == subject_id)
    if statuses:
        stmt = stmt.where(StructType.status.in_(list(statuses)))
    return list((await db.execute(stmt.order_by(StructType.sort_order, StructType.id))).scalars().all())


async def get_type(db: AsyncSession, type_id: int) -> StructType:
    """按 id 取类型,不存在抛 NotFound。"""
    found = await db.get(StructType, type_id)
    if found is None:
        raise NotFound("Structure type not found", ErrorCode.STRUCTURE_TYPE_NOT_FOUND)
    return found


async def usage_counts(db: AsyncSession, subject_id: int) -> Dict[int, int]:
    """每个类型被多少道(已采纳拆解的)题 / 材料引用:{type_id: 数量}。"""
    counts: Dict[int, set] = {}
    for model in (StructElement, StructAsk):
        rows = await db.execute(
            select(model.type_id, StructRun.target_type, StructRun.target_id)
            .join(StructRun, model.run_id == StructRun.id)
            .where(
                StructRun.subject_id == subject_id,
                StructRun.state == StructRunState.ACCEPTED.value,
                model.type_id.is_not(None),
            )
            .distinct()
        )
        for type_id, target_type, target_id in rows.all():
            counts.setdefault(type_id, set()).add((target_type, target_id))
    # 方法类型:被已采纳解答的步骤引用的题数。
    from app.models.solution_structure import SolutionRun, SolutionStep

    rows = await db.execute(
        select(SolutionStep.method_type_id, SolutionRun.question_id)
        .join(SolutionRun, SolutionStep.run_id == SolutionRun.id)
        .where(
            SolutionRun.subject_id == subject_id,
            SolutionRun.state == StructRunState.ACCEPTED.value,
            SolutionStep.method_type_id.is_not(None),
        )
        .distinct()
    )
    for type_id, question_id in rows.all():
        counts.setdefault(type_id, set()).add(("question", question_id))
    return {type_id: len(targets) for type_id, targets in counts.items()}


def descendants(types: Iterable[StructType], root_ids: Iterable[int]) -> set:
    """给定节点及其全部子孙的 id(筛选「代数」时也要命中代数下的子类型)。"""
    children: Dict[Optional[int], List[int]] = {}
    for t in types:
        children.setdefault(t.parent_id, []).append(t.id)
    found: set = set()
    stack = list(root_ids)
    while stack:
        current = stack.pop()
        if current in found:
            continue
        found.add(current)
        stack.extend(children.get(current, []))
    return found


def path_names(types: Sequence[StructType]) -> Dict[int, List[str]]:
    """每个类型从根到自身的名称路径,如 {7: ["代数", "函数", "含参三次函数"]}。"""
    by_id = {t.id: t for t in types}
    paths: Dict[int, List[str]] = {}
    for t in types:
        names: List[str] = []
        current: Optional[StructType] = t
        guard = 0
        while current is not None and guard < 64:
            names.append(current.name)
            current = by_id.get(current.parent_id) if current.parent_id else None
            guard += 1
        paths[t.id] = list(reversed(names))
    return paths


def tree_text(types: Sequence[StructType], kind: StructTypeKind) -> str:
    """把某一类(条件 / 设问 / 方法)的 active 类型渲染成缩进列表,供提示词使用。

    形如 ``- algebra: 代数 — 式的结构……``,子类型多缩进两格。
    """
    active = [t for t in types if t.kind == kind.value and t.status == StructTypeStatus.ACTIVE.value]
    children: Dict[Optional[int], List[StructType]] = {}
    ids = {t.id for t in active}
    for t in active:
        parent = t.parent_id if t.parent_id in ids else None
        children.setdefault(parent, []).append(t)
    lines: List[str] = []

    def walk(parent: Optional[int], depth: int) -> None:
        for t in children.get(parent, []):
            definition = f" — {t.definition}" if t.definition else ""
            weight = f" (weight {t.weight:g})" if kind == StructTypeKind.METHOD and t.weight not in (None, 1) else ""
            lines.append(f"{'  ' * depth}- {t.code}: {t.name}{weight}{definition}")
            walk(t.id, depth + 1)

    walk(None, 0)
    return "\n".join(lines)

# endregion


# region 修改

async def create_type(
    db: AsyncSession,
    *,
    subject_id: int,
    name: str,
    kind: Optional[str] = None,
    parent_id: Optional[int] = None,
    code: Optional[str] = None,
    definition: Optional[str] = None,
    examples: Optional[List[Dict[str, Any]]] = None,
    status: str = StructTypeStatus.ACTIVE.value,
    sort_order: Optional[int] = None,
    created_by: Optional[int] = None,
    weight: Optional[float] = None,
) -> StructType:
    """新建类型并提交。``kind`` 缺省时继承父节点;``code`` 缺省时由名称生成。"""
    parent = await _valid_parent(db, subject_id, parent_id) if parent_id else None
    kind = kind or (parent.kind if parent else StructTypeKind.CONDITION.value)
    if parent is not None and parent.kind != kind:
        raise Invalid("Child type must have the same kind as its parent", ErrorCode.STRUCTURE_TYPE_INVALID_PARENT)
    _validate_enum(kind, StructTypeKind)
    _validate_enum(status, StructTypeStatus)
    code = (code or "").strip() or await _generate_code(db, subject_id, name)
    if await _code_taken(db, subject_id, code):
        raise Conflict("Type code already exists", ErrorCode.STRUCTURE_TYPE_CODE_EXISTS, {"code": code})
    if sort_order is None:
        # 新类型排在同级的最后。
        same_parent = StructType.parent_id.is_(None) if parent is None else StructType.parent_id == parent.id
        sort_order = (await db.scalar(
            select(func.max(StructType.sort_order)).where(StructType.subject_id == subject_id, same_parent)
        ) or 0) + 1
    created = StructType(
        subject_id=subject_id,
        parent_id=parent.id if parent else None,
        kind=kind,
        code=code,
        name=name.strip(),
        definition=(definition or None),
        examples=json.dumps(examples, ensure_ascii=False) if examples else None,
        status=status,
        sort_order=sort_order,
        created_by=created_by,
        weight=_valid_weight(weight),
    )
    db.add(created)
    await db.commit()
    await db.refresh(created)
    return created


async def update_type(db: AsyncSession, target: StructType, changes: Dict[str, Any]) -> StructType:
    """修改类型并提交。支持 name / definition / examples / status / sort_order / parent_id(移动)。

    移动时不允许挂到自己或自己的子孙下面,也不允许跨 kind(条件类型不能挂到设问下)。
    """
    if "parent_id" in changes:
        new_parent_id = changes["parent_id"]
        if new_parent_id is not None:
            parent = await _valid_parent(db, target.subject_id, new_parent_id)
            subtree = descendants(await list_types(db, target.subject_id), [target.id])
            if parent.id in subtree:
                raise Invalid("A type cannot be moved under itself", ErrorCode.STRUCTURE_TYPE_INVALID_PARENT)
            if parent.kind != target.kind:
                raise Invalid("Parent type must have the same kind", ErrorCode.STRUCTURE_TYPE_INVALID_PARENT)
        target.parent_id = new_parent_id
    if "name" in changes and changes["name"]:
        target.name = str(changes["name"]).strip()
    if "definition" in changes:
        target.definition = changes["definition"] or None
    if "examples" in changes:
        target.examples = json.dumps(changes["examples"], ensure_ascii=False) if changes["examples"] else None
    if "status" in changes and changes["status"]:
        _validate_enum(changes["status"], StructTypeStatus)
        target.status = changes["status"]
    if "sort_order" in changes and changes["sort_order"] is not None:
        target.sort_order = int(changes["sort_order"])
    if changes.get("knowledge_point_ids") is not None:
        await set_knowledge_points(db, target, changes["knowledge_point_ids"])
    weight_changed = False
    if "weight" in changes and changes["weight"] is not None:
        weight = _valid_weight(changes["weight"])
        weight_changed = weight != target.weight
        target.weight = weight
    await db.commit()
    if weight_changed:
        # 权重变化:用到该方法的已采纳解答重算思维量。
        from .solution import recompute_for_method

        await recompute_for_method(db, target.id)
    await db.refresh(target)
    return target


async def knowledge_point_map(db: AsyncSession, subject_id: int) -> Dict[int, List[int]]:
    """学科内每个类型映射的知识点 id(规格 §12.3 N8)。"""
    rows = await db.execute(
        select(StructTypeKnowledgePoint.type_id, StructTypeKnowledgePoint.knowledge_point_id)
        .join(StructType, StructType.id == StructTypeKnowledgePoint.type_id)
        .where(StructType.subject_id == subject_id)
        .order_by(StructTypeKnowledgePoint.knowledge_point_id)
    )
    out: Dict[int, List[int]] = {}
    for type_id, kp_id in rows.all():
        out.setdefault(type_id, []).append(kp_id)
    return out


async def set_knowledge_points(db: AsyncSession, target: StructType, kp_ids: Sequence[int]) -> None:
    """替换类型映射的知识点(只接受本学科的知识点)。不提交。"""
    from app.models.knowledge_point import KnowledgePoint

    ids = list(dict.fromkeys(int(i) for i in kp_ids))
    if ids:
        valid = set((await db.execute(
            select(KnowledgePoint.id).where(KnowledgePoint.id.in_(ids), KnowledgePoint.subject_id == target.subject_id)
        )).scalars().all())
        if len(valid) != len(ids):
            raise Invalid("Unknown knowledge point", ErrorCode.STRUCTURE_INVALID_ITEM)
    await db.execute(delete(StructTypeKnowledgePoint).where(StructTypeKnowledgePoint.type_id == target.id))
    for kp_id in ids:
        db.add(StructTypeKnowledgePoint(type_id=target.id, knowledge_point_id=kp_id))
    await db.flush()


async def merge_types(db: AsyncSession, source: StructType, target: StructType) -> StructType:
    """把 source 合并进 target:引用改指向 target,子节点移到 target 下,删除 source。提交。"""
    if source.id == target.id or source.subject_id != target.subject_id or source.kind != target.kind:
        raise Invalid("Types cannot be merged", ErrorCode.STRUCTURE_TYPE_INVALID_PARENT)
    if target.id in descendants(await list_types(db, source.subject_id), [source.id]):
        raise Invalid("Cannot merge a type into its own descendant", ErrorCode.STRUCTURE_TYPE_INVALID_PARENT)
    for model in (StructElement, StructAsk):
        await db.execute(
            update(model).where(model.type_id == source.id).values(type_id=target.id)
            .execution_options(synchronize_session=False)
        )
    await db.execute(
        update(StructType).where(StructType.parent_id == source.id).values(parent_id=target.id)
        .execution_options(synchronize_session=False)
    )
    # 知识点映射并入目标类型(去重),解答步骤的方法引用也改指向目标。
    from app.models.solution_structure import SolutionStep

    have = set((await db.execute(
        select(StructTypeKnowledgePoint.knowledge_point_id).where(StructTypeKnowledgePoint.type_id == target.id)
    )).scalars().all())
    moved = (await db.execute(
        select(StructTypeKnowledgePoint.knowledge_point_id).where(StructTypeKnowledgePoint.type_id == source.id)
    )).scalars().all()
    for kp_id in moved:
        if kp_id not in have:
            db.add(StructTypeKnowledgePoint(type_id=target.id, knowledge_point_id=kp_id))
    await db.execute(
        update(SolutionStep).where(SolutionStep.method_type_id == source.id).values(method_type_id=target.id)
        .execution_options(synchronize_session=False)
    )
    await db.delete(source)
    await db.commit()
    await db.refresh(target)
    return target


async def delete_type(db: AsyncSession, target: StructType) -> None:
    """删除类型并提交。有子节点或仍被拆解引用时拒绝——请改用停用或合并,避免丢失分类。"""
    if await db.scalar(select(StructType.id).where(StructType.parent_id == target.id).limit(1)) is not None:
        raise Conflict("Type has children", ErrorCode.STRUCTURE_TYPE_HAS_CHILDREN)
    from app.models.solution_structure import SolutionStep

    for column in (StructElement.type_id, StructAsk.type_id, SolutionStep.method_type_id):
        if await db.scalar(select(column).where(column == target.id).limit(1)) is not None:
            raise Conflict("Type is in use", ErrorCode.STRUCTURE_TYPE_IN_USE)
    await db.delete(target)
    await db.commit()


async def export_types(db: AsyncSession, subject_id: int) -> List[Dict[str, Any]]:
    """导出为可再次导入的列表(父节点用 code 引用,父在子前)。"""
    types = await list_types(db, subject_id)
    by_id = {t.id: t for t in types}
    ordered: List[StructType] = []
    seen: set = set()

    def visit(t: StructType) -> None:
        if t.id in seen:
            return
        if t.parent_id in by_id:
            visit(by_id[t.parent_id])
        seen.add(t.id)
        ordered.append(t)

    for t in types:
        visit(t)
    return [
        {
            "code": t.code,
            "name": t.name,
            "kind": t.kind,
            "parent_code": by_id[t.parent_id].code if t.parent_id in by_id else None,
            "definition": t.definition,
            "examples": parse_examples(t.examples),
            "status": t.status,
            "sort_order": t.sort_order,
            "weight": t.weight,
        }
        for t in ordered
    ]


async def import_types(
    db: AsyncSession, subject_id: int, items: Sequence[Dict[str, Any]], *, created_by: Optional[int] = None
) -> Dict[str, int]:
    """按 code 导入(已存在则更新名称、定义、示例、状态与父节点),提交。返回新增 / 更新数量。

    列表中父节点可以出现在子节点之后;整个导入在一个事务里,任何一条无效都整体回滚。
    """
    existing = {t.code: t for t in await list_types(db, subject_id)}
    pending = [dict(item) for item in items]
    created = updated = 0
    # 多轮处理:每一轮处理父节点已就绪的条目,直到全部处理完或无法再前进。
    while pending:
        progressed = False
        remaining: List[Dict[str, Any]] = []
        for item in pending:
            code = str(item.get("code") or "").strip()
            name = str(item.get("name") or "").strip()
            if not code or not name or not re.fullmatch(r"[A-Za-z0-9_.\-]{1,64}", code):
                await db.rollback()
                raise Invalid("Invalid type entry", ErrorCode.STRUCTURE_TYPE_INVALID_IMPORT, {"code": code})
            parent_code = item.get("parent_code")
            if parent_code and parent_code not in existing:
                remaining.append(item)
                continue
            parent = existing.get(parent_code) if parent_code else None
            kind = item.get("kind") or (parent.kind if parent else StructTypeKind.CONDITION.value)
            status = item.get("status") or StructTypeStatus.ACTIVE.value
            try:
                _validate_enum(kind, StructTypeKind)
                _validate_enum(status, StructTypeStatus)
            except Invalid:
                await db.rollback()
                raise Invalid("Invalid type entry", ErrorCode.STRUCTURE_TYPE_INVALID_IMPORT, {"code": code})
            if parent is not None and parent.kind != kind:
                await db.rollback()
                raise Invalid("Invalid type entry", ErrorCode.STRUCTURE_TYPE_INVALID_IMPORT, {"code": code})
            examples = item.get("examples")
            values = dict(
                name=name,
                kind=kind,
                parent_id=parent.id if parent else None,
                definition=item.get("definition") or None,
                examples=json.dumps(examples, ensure_ascii=False) if examples else None,
                status=status,
                sort_order=int(item.get("sort_order") or 0),
                weight=_valid_weight(item.get("weight")),
            )
            current = existing.get(code)
            if current is None:
                current = StructType(subject_id=subject_id, code=code, created_by=created_by, **values)
                db.add(current)
                await db.flush()
                existing[code] = current
                created += 1
            else:
                for key, value in values.items():
                    setattr(current, key, value)
                updated += 1
            progressed = True
        if not progressed:
            await db.rollback()
            raise Invalid(
                "Unknown parent type", ErrorCode.STRUCTURE_TYPE_INVALID_IMPORT,
                {"code": str(remaining[0].get("parent_code"))},
            )
        pending = remaining
    await db.commit()
    return {"created": created, "updated": updated}

# endregion


# region 内部实现

def _valid_weight(value: Any) -> float:
    """权重:正数,缺省为 1。"""
    if value in (None, ""):
        return 1.0
    try:
        weight = float(value)
    except (TypeError, ValueError):
        raise Invalid("Weight must be a positive number", ErrorCode.STRUCTURE_INVALID_ITEM)
    if not 0 < weight <= 100:
        raise Invalid("Weight must be a positive number", ErrorCode.STRUCTURE_INVALID_ITEM)
    return round(weight, 2)


def _is_math(subject: Subject) -> bool:
    text = f"{subject.slug or ''} {subject.name or ''}".lower()
    return any(hint in text for hint in _MATH_HINTS)


def _validate_enum(value: str, enum_cls: Any) -> None:
    if value not in {member.value for member in enum_cls}:
        raise Invalid(f"Invalid value: {value}", ErrorCode.STRUCTURE_INVALID_ITEM)


def parse_examples(raw: Optional[str]) -> Optional[List[Any]]:
    """解析类型的示例(JSON 数组字符串);为空或损坏时返回 None。"""
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except ValueError:
        return None
    return value if isinstance(value, list) else None


async def _valid_parent(db: AsyncSession, subject_id: int, parent_id: int) -> StructType:
    parent = await db.get(StructType, parent_id)
    if parent is None or parent.subject_id != subject_id:
        raise Invalid("Parent type not found in this subject", ErrorCode.STRUCTURE_TYPE_INVALID_PARENT)
    return parent


async def _code_taken(db: AsyncSession, subject_id: int, code: str) -> bool:
    return await db.scalar(
        select(StructType.id).where(StructType.subject_id == subject_id, StructType.code == code).limit(1)
    ) is not None


async def _generate_code(db: AsyncSession, subject_id: int, name: str) -> str:
    """由名称生成学科内唯一的 code:ASCII 名称直接转小写下划线,其余用 t_序号。"""
    base = re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")[:48]
    if not base:
        count = await db.scalar(select(func.count(StructType.id)).where(StructType.subject_id == subject_id))
        base = f"t_{(count or 0) + 1}"
    code = base
    suffix = 2
    while await _code_taken(db, subject_id, code):
        code = f"{base}_{suffix}"
        suffix += 1
    return code

# endregion
