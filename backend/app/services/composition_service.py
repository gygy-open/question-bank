"""组稿 (Composition) 域的领域服务 —— AST 阶段。

职责边界(与 crud_composition 划分):
- crud 负责 scoped 读取(强制 subject/scope/owner)。
- 本模块负责 **写路径的领域不变量与事务**:父目录一致性、自引用/祖先环检测、
  软删除非空拦截、组稿乐观锁(条件 UPDATE),AST 全量校验/规范化,以及与业务变更
  **同事务** 写 CompositionEvent。

错误约定(与仓库 FastAPI 风格一致):
- 跨 scope/subject/owner 不可见 → 404(防枚举)。
- 版本冲突 / 删除非空目录 → 409。
- 结构非法(自引用父、祖先环、AST 违规)→ 400。
- 引用题目缺失/跨学科 → 422。
"""
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import crud_composition
from app.models.composition import (
    BODY_SLOT,
    Composition,
    CompositionEvent,
    CompositionNode,
    CompositionNodeKind,
    CompositionVersion,
    Folder,
    NODE_TYPE_ANSWER_ITEM,
    NODE_TYPE_HEADING,
    NODE_TYPE_QUESTION,
    NODE_TYPE_QUESTION_DETAILS,
    NODE_TYPE_RICH_TEXT,
    ScopeType,
)
from app.models.question import Question, QuestionType
from app.models.user import User
from app.schemas.composition import (
    ANSWER_FIELD_KEYS,
    CompositionNodeInput,
    QuestionContentSnapshot,
    QuestionSnapshot,
)
from app.services.question_content import parse_json_field

SNAPSHOT_SCHEMA_VERSION = 2


# --------------------------------------------------------------------------- #
# 内部工具
# --------------------------------------------------------------------------- #
def _not_found(what: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} not found")


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)


async def _resolve_scoped_parent(
    db: AsyncSession,
    *,
    parent_id: int,
    subject_id: int,
    scope_type: ScopeType,
    owner_id: Optional[int],
) -> Folder:
    """父目录必须与目标在同一 subject/scope/owner,且未删除。否则 404(防枚举)。"""
    parent = await crud_composition.folder.get_scoped(
        db,
        folder_id=parent_id,
        subject_id=subject_id,
        scope_type=scope_type,
        owner_id=owner_id,
    )
    if parent is None:
        raise _not_found("Parent folder")
    return parent


async def _would_create_cycle(
    db: AsyncSession,
    *,
    folder_id: int,
    new_parent_id: int,
    subject_id: int,
    scope_type: ScopeType,
    owner_id: Optional[int],
) -> bool:
    """从 new_parent 沿 parent_id 向上遍历;若遇到 folder_id 则会成环。"""
    cursor: Optional[int] = new_parent_id
    # 上限步数与遍历过的节点集合共同防御脏数据造成的死循环。
    seen: set[int] = set()
    while cursor is not None:
        if cursor == folder_id:
            return True
        if cursor in seen:
            break
        seen.add(cursor)
        node = await crud_composition.folder.get_scoped(
            db,
            folder_id=cursor,
            subject_id=subject_id,
            scope_type=scope_type,
            owner_id=owner_id,
        )
        if node is None:
            break
        cursor = node.parent_id
    return False


async def _add_event(
    db: AsyncSession,
    *,
    composition_id: int,
    composition_revision: int,
    event_type: str,
    summary: str,
    actor_id: int,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    payload: Optional[dict] = None,
    batch_id: Optional[str] = None,
) -> None:
    """加入当前事务(不 commit),由调用方统一提交,保证与业务变更同事务。"""
    db.add(
        CompositionEvent(
            composition_id=composition_id,
            composition_revision=composition_revision,
            event_type=event_type,
            target_type=target_type,
            target_id=target_id,
            summary=summary,
            payload=payload,
            batch_id=batch_id,
            actor_id=actor_id,
        )
    )


# --------------------------------------------------------------------------- #
# Folder
# --------------------------------------------------------------------------- #
async def create_folder(
    db: AsyncSession,
    *,
    subject_id: int,
    scope_type: ScopeType,
    owner_id: Optional[int],
    actor: User,
    name: str,
    parent_id: Optional[int],
) -> Folder:
    if parent_id is not None:
        await _resolve_scoped_parent(
            db,
            parent_id=parent_id,
            subject_id=subject_id,
            scope_type=scope_type,
            owner_id=owner_id,
        )
    folder = Folder(
        name=name,
        scope_type=scope_type,
        owner_id=owner_id,
        subject_id=subject_id,
        parent_id=parent_id,
        created_by=actor.id,
        updated_by=actor.id,
    )
    db.add(folder)
    await db.commit()
    await db.refresh(folder)
    return folder


async def update_folder(
    db: AsyncSession,
    *,
    folder: Folder,
    actor: User,
    name: Optional[str] = None,
    parent_id: Optional[int] = None,
    parent_id_provided: bool = False,
) -> Folder:
    if name is not None:
        folder.name = name

    if parent_id_provided:
        if parent_id is not None:
            if parent_id == folder.id:
                raise _bad_request("A folder cannot be its own parent")
            await _resolve_scoped_parent(
                db,
                parent_id=parent_id,
                subject_id=folder.subject_id,
                scope_type=folder.scope_type,
                owner_id=folder.owner_id,
            )
            if await _would_create_cycle(
                db,
                folder_id=folder.id,
                new_parent_id=parent_id,
                subject_id=folder.subject_id,
                scope_type=folder.scope_type,
                owner_id=folder.owner_id,
            ):
                raise _bad_request("Moving folder would create a cycle")
        folder.parent_id = parent_id

    folder.updated_by = actor.id
    db.add(folder)
    await db.commit()
    await db.refresh(folder)
    return folder


async def delete_folder(
    db: AsyncSession,
    *,
    folder: Folder,
    actor: User,
) -> None:
    """软删除;若存在未删除的子目录或组稿则 409,不级联。"""
    active_children = await crud_composition.folder.count_active_children(
        db, folder_id=folder.id
    )
    if active_children > 0:
        raise _conflict("Folder is not empty")
    folder.deleted_at = datetime.utcnow()
    folder.updated_by = actor.id
    db.add(folder)
    await db.commit()


# --------------------------------------------------------------------------- #
# Composition
# --------------------------------------------------------------------------- #
async def _validate_folder_ref(
    db: AsyncSession,
    *,
    folder_id: int,
    subject_id: int,
    scope_type: ScopeType,
    owner_id: Optional[int],
) -> None:
    ref = await crud_composition.folder.get_scoped(
        db,
        folder_id=folder_id,
        subject_id=subject_id,
        scope_type=scope_type,
        owner_id=owner_id,
    )
    if ref is None:
        raise _not_found("Folder")


async def create_composition(
    db: AsyncSession,
    *,
    subject_id: int,
    scope_type: ScopeType,
    owner_id: Optional[int],
    actor: User,
    title: str,
    description: Optional[str],
    folder_id: Optional[int],
) -> Composition:
    if folder_id is not None:
        await _validate_folder_ref(
            db,
            folder_id=folder_id,
            subject_id=subject_id,
            scope_type=scope_type,
            owner_id=owner_id,
        )
    comp = Composition(
        title=title,
        description=description,
        scope_type=scope_type,
        owner_id=owner_id,
        subject_id=subject_id,
        folder_id=folder_id,
        revision=1,
        created_by=actor.id,
        updated_by=actor.id,
    )
    db.add(comp)
    await db.flush()
    await _add_event(
        db,
        composition_id=comp.id,
        composition_revision=comp.revision,
        event_type="created",
        summary=f"Created composition “{title}”",
        actor_id=actor.id,
    )
    await db.commit()
    await db.refresh(comp)
    return comp


async def _guarded_write(
    db: AsyncSession,
    *,
    composition_id: int,
    expected_revision: int,
    values: dict,
    require_deleted: Optional[bool] = None,
) -> int:
    """乐观锁条件 UPDATE:仅当 revision 匹配(且删除态符合要求)时生效并自增 revision。

    返回新的 revision;若无行被更新(并发或删除态不符)抛 409。
    """
    stmt = (
        update(Composition)
        .where(
            Composition.id == composition_id,
            Composition.revision == expected_revision,
        )
        .values(**values, revision=Composition.revision + 1)
    )
    if require_deleted is True:
        stmt = stmt.where(Composition.deleted_at.is_not(None))
    elif require_deleted is False:
        stmt = stmt.where(Composition.deleted_at.is_(None))
    result = await db.execute(stmt)
    if result.rowcount == 0:
        raise _conflict("Composition revision mismatch")
    return expected_revision + 1


async def update_composition(
    db: AsyncSession,
    *,
    comp: Composition,
    actor: User,
    expected_revision: int,
    title: Optional[str] = None,
    description: Optional[str] = None,
    status_value: Optional[str] = None,
    folder_id: Optional[int] = None,
    folder_id_provided: bool = False,
) -> Composition:
    values: dict = {"updated_by": actor.id, "updated_at": datetime.utcnow()}
    moved = False
    if title is not None:
        values["title"] = title
    if description is not None:
        values["description"] = description
    if status_value is not None:
        values["status"] = status_value
    if folder_id_provided:
        if folder_id is not None:
            await _validate_folder_ref(
                db,
                folder_id=folder_id,
                subject_id=comp.subject_id,
                scope_type=comp.scope_type,
                owner_id=comp.owner_id,
            )
        moved = folder_id != comp.folder_id
        values["folder_id"] = folder_id

    new_revision = await _guarded_write(
        db,
        composition_id=comp.id,
        expected_revision=expected_revision,
        values=values,
        require_deleted=False,
    )
    await _add_event(
        db,
        composition_id=comp.id,
        composition_revision=new_revision,
        event_type="moved" if moved else "updated",
        summary=(
            f"Moved composition to folder {folder_id}" if moved else "Updated composition metadata"
        ),
        actor_id=actor.id,
    )
    await db.commit()
    refreshed = await crud_composition.composition.get_scoped(
        db,
        composition_id=comp.id,
        subject_id=comp.subject_id,
        scope_type=comp.scope_type,
        owner_id=comp.owner_id,
    )
    assert refreshed is not None
    return refreshed


async def delete_composition(
    db: AsyncSession,
    *,
    comp: Composition,
    actor: User,
    expected_revision: int,
) -> None:
    new_revision = await _guarded_write(
        db,
        composition_id=comp.id,
        expected_revision=expected_revision,
        values={
            "deleted_at": datetime.utcnow(),
            "updated_by": actor.id,
            "updated_at": datetime.utcnow(),
        },
        require_deleted=False,
    )
    await _add_event(
        db,
        composition_id=comp.id,
        composition_revision=new_revision,
        event_type="deleted",
        summary="Deleted composition",
        actor_id=actor.id,
    )
    await db.commit()


async def restore_composition(
    db: AsyncSession,
    *,
    comp: Composition,
    actor: User,
    expected_revision: int,
) -> Composition:
    new_revision = await _guarded_write(
        db,
        composition_id=comp.id,
        expected_revision=expected_revision,
        values={
            "deleted_at": None,
            "updated_by": actor.id,
            "updated_at": datetime.utcnow(),
        },
        require_deleted=True,
    )
    await _add_event(
        db,
        composition_id=comp.id,
        composition_revision=new_revision,
        event_type="restored",
        summary="Restored composition",
        actor_id=actor.id,
    )
    await db.commit()
    refreshed = await crud_composition.composition.get_scoped(
        db,
        composition_id=comp.id,
        subject_id=comp.subject_id,
        scope_type=comp.scope_type,
        owner_id=comp.owner_id,
    )
    assert refreshed is not None
    return refreshed


# --------------------------------------------------------------------------- #
# 题目内容快照(冻结)
# --------------------------------------------------------------------------- #
def _build_question_content_snapshot(question: Question) -> Dict[str, Any]:
    """把实时题目冻结为 question 节点的内容快照(不含 id/revision)。"""
    q_type = question.q_type.value if isinstance(question.q_type, QuestionType) else question.q_type
    snapshot = QuestionContentSnapshot(
        content_schema_version=int(question.content_schema_version or 0),
        q_type=q_type,
        content=parse_json_field(question.content),
        options=question.options,
        answer=parse_json_field(question.answer),
        thinking=parse_json_field(question.thinking),
        analysis=parse_json_field(question.analysis),
        summary=parse_json_field(question.summary),
        difficulty=int(question.difficulty) if question.difficulty is not None else 1,
        source=question.source,
    )
    return snapshot.model_dump()


async def _load_scoped_question(
    db: AsyncSession,
    *,
    question_id: int,
    subject_id: int,
) -> Question:
    """校验 question 节点引用并返回实时题目。

    缺失 / 软删除 / 跨学科统一 422(不信任客户端传入的 revision/快照)。
    """
    result = await db.execute(
        select(Question).where(
            Question.id == question_id,
            Question.deleted_at.is_(None),
        )
    )
    question = result.scalars().first()
    if question is None:
        raise _unprocessable(f"question {question_id} not found or deleted")
    if question.subject_id != subject_id:
        raise _unprocessable(f"question {question_id} belongs to a different subject")
    return question


# --------------------------------------------------------------------------- #
# CompositionNode 整体替换(AST 契约)
# --------------------------------------------------------------------------- #
def _default_answer_item_props() -> Dict[str, Any]:
    return {"included": True, "overrides": {key: None for key in ANSWER_FIELD_KEYS}}


def _validate_ast(items: List[CompositionNodeInput]) -> None:
    """全量内存校验 AST(不产生任何写入)。

    每个节点单体规则已由 schema 保证;这里补齐跨节点不变量:父存在且为同稿
    question_details module、reference source 指向同稿 root 层 question 节点、
    自定义节点 anchor 指向同 module 内 answer_item。
    """
    by_id = {it.id: it for it in items}
    for it in items:
        if it.parent_id is not None:
            parent = by_id.get(it.parent_id)
            if parent is None:
                raise _bad_request(f"node {it.id} references a missing parent")
            if parent.node_type != NODE_TYPE_QUESTION_DETAILS:
                raise _bad_request(
                    f"node {it.id} parent must be a question_details module"
                )
        if it.node_type == NODE_TYPE_ANSWER_ITEM:
            src = by_id.get(it.source_question_node_id)
            if src is None or src.node_type != NODE_TYPE_QUESTION or src.parent_id is not None:
                raise _bad_request(
                    f"answer_item {it.id} source must point to a root-level question node"
                )
        if it.anchor_before_node_id is not None:
            target = by_id.get(it.anchor_before_node_id)
            if (
                target is None
                or target.node_type != NODE_TYPE_ANSWER_ITEM
                or target.parent_id != it.parent_id
            ):
                raise _bad_request(
                    f"node {it.id} anchor must point to an answer_item in the same module"
                )


def _normalize_module_children(
    module: CompositionNodeInput,
    *,
    root_question_items: List[CompositionNodeInput],
    module_root_index: int,
    root_index_by_id: Dict[str, int],
    children: List[CompositionNodeInput],
) -> List[Dict[str, Any]]:
    """按 module scope 规范化 question_details 的子节点顺序与 answer_item 集合。

    - scope=all → 整稿全部 root 层 question 节点;scope=before → module 之前的。
    - 每个范围内 question 节点产出一条 answer_item(重复 question_id 因节点不同而各自保留)。
    - answer_item 相对顺序跟随正文(题序)。
    - 尽量复用客户端传入的 answer_item(按 source_question_node_id 顺序消费)以保留
      id / included / overrides;不足则服务端生成新 UUID + 默认 props。
    - 自定义 heading/rich_text 按 anchor_before_node_id 混排,悬空锚点落到末尾(保序)。

    返回子节点规范化描述列表(dict),position 由列表下标决定。
    """
    scope = (module.props or {}).get("scope")
    if scope == "all":
        scoped_questions = list(root_question_items)
    else:  # before
        scoped_questions = [
            q for q in root_question_items
            if root_index_by_id[q.id] < module_root_index
        ]

    # 客户端 answer_item 按 source 分组,保留请求顺序以支持重复消费。
    client_ai_by_source: Dict[str, List[CompositionNodeInput]] = defaultdict(list)
    for child in children:
        if child.node_type == NODE_TYPE_ANSWER_ITEM:
            client_ai_by_source[child.source_question_node_id].append(child)

    answer_items: List[Dict[str, Any]] = []
    for q in scoped_questions:
        pool = client_ai_by_source.get(q.id)
        if pool:
            reused = pool.pop(0)
            answer_items.append(
                {
                    "id": reused.id,
                    "source_question_node_id": q.id,
                    "props": reused.props or _default_answer_item_props(),
                    "schema_version": reused.schema_version,
                }
            )
        else:
            answer_items.append(
                {
                    "id": str(uuid.uuid4()),
                    "source_question_node_id": q.id,
                    "props": _default_answer_item_props(),
                    "schema_version": 1,
                }
            )

    final_ai_ids = {ai["id"] for ai in answer_items}
    custom = [c for c in children if c.node_type in (NODE_TYPE_HEADING, NODE_TYPE_RICH_TEXT)]
    anchored: Dict[str, List[CompositionNodeInput]] = defaultdict(list)
    trailing: List[CompositionNodeInput] = []
    for c in custom:
        if c.anchor_before_node_id in final_ai_ids:
            anchored[c.anchor_before_node_id].append(c)
        else:
            trailing.append(c)

    ordered: List[Dict[str, Any]] = []
    for ai in answer_items:
        for c in anchored.get(ai["id"], []):
            ordered.append({"kind": "custom", "item": c})
        ordered.append({"kind": "answer_item", **ai})
    for c in trailing:
        ordered.append({"kind": "custom", "item": c})
    return ordered


async def replace_nodes(
    db: AsyncSession,
    *,
    comp: Composition,
    actor: User,
    expected_revision: int,
    batch_id: Optional[str],
    items: List[CompositionNodeInput],
) -> tuple[int, List[CompositionNode]]:
    """一次事务内整体替换 composition 的节点 AST。

    流程:全量内存校验 → 冻结 question 快照 → 乐观锁自增 revision → 删旧建新
    (root 先、module 子后,满足自引用 FK)→ 规范化 module 的 answer_item → 写事件。
    任何校验失败不产生部分更改;组稿乐观锁冲突 409。
    """
    # 1) 全量 AST 校验(纯内存)。
    _validate_ast(items)

    existing = await crud_composition.composition.list_nodes(db, composition_id=comp.id)
    existing_by_id = {n.id: n for n in existing}

    # 2) 冻结 question 快照计划:新建 / question_id 变化 → 读实时题目;否则保留 DB 快照。
    question_plan: Dict[str, Optional[tuple[int, Dict[str, Any]]]] = {}
    for it in items:
        if it.node_type != NODE_TYPE_QUESTION:
            continue
        assert it.question_id is not None  # schema 已保证
        prev = existing_by_id.get(it.id)
        if (
            prev is not None
            and prev.node_type == NODE_TYPE_QUESTION
            and prev.question_id == it.question_id
            and prev.content is not None
        ):
            question_plan[it.id] = None  # 保留 DB 快照与 revision
        else:
            question = await _load_scoped_question(
                db, question_id=it.question_id, subject_id=comp.subject_id
            )
            question_plan[it.id] = (
                int(question.content_revision or 1),
                _build_question_content_snapshot(question),
            )

    # 3) 乐观锁:先条件自增 revision;冲突则 409 且此时尚未改动任何节点。
    new_revision = await _guarded_write(
        db,
        composition_id=comp.id,
        expected_revision=expected_revision,
        values={"updated_by": actor.id, "updated_at": datetime.utcnow()},
        require_deleted=False,
    )

    # 4) 计算新 AST 布局。
    root_items = [it for it in items if it.parent_id is None]
    root_index_by_id = {it.id: idx for idx, it in enumerate(root_items)}
    root_question_items = [it for it in root_items if it.node_type == NODE_TYPE_QUESTION]
    children_by_parent: Dict[str, List[CompositionNodeInput]] = defaultdict(list)
    for it in items:
        if it.parent_id is not None:
            children_by_parent[it.parent_id].append(it)

    def _new_node(**kwargs: Any) -> CompositionNode:
        return CompositionNode(
            composition_id=comp.id,
            created_by=actor.id,
            updated_by=actor.id,
            **kwargs,
        )

    root_nodes: List[CompositionNode] = []
    child_nodes: List[CompositionNode] = []

    for root_idx, it in enumerate(root_items):
        if it.node_type == NODE_TYPE_QUESTION:
            plan = question_plan[it.id]
            if plan is None:
                prev = existing_by_id[it.id]
                content = prev.content
                revision = prev.question_revision
            else:
                revision, content = plan
            root_nodes.append(
                _new_node(
                    id=it.id,
                    parent_id=None,
                    slot=None,
                    position=root_idx,
                    node_kind=CompositionNodeKind.BLOCK,
                    node_type=NODE_TYPE_QUESTION,
                    content=content,
                    props=None,
                    schema_version=it.schema_version,
                    question_id=it.question_id,
                    question_revision=revision,
                )
            )
        else:
            root_nodes.append(
                _new_node(
                    id=it.id,
                    parent_id=None,
                    slot=None,
                    position=root_idx,
                    node_kind=it.node_kind,
                    node_type=it.node_type,
                    content=it.content,
                    props=it.props,
                    schema_version=it.schema_version,
                )
            )

    for it in root_items:
        if it.node_type != NODE_TYPE_QUESTION_DETAILS:
            continue
        ordered = _normalize_module_children(
            it,
            root_question_items=root_question_items,
            module_root_index=root_index_by_id[it.id],
            root_index_by_id=root_index_by_id,
            children=children_by_parent.get(it.id, []),
        )
        for pos, entry in enumerate(ordered):
            if entry["kind"] == "answer_item":
                child_nodes.append(
                    _new_node(
                        id=entry["id"],
                        parent_id=it.id,
                        slot=BODY_SLOT,
                        position=pos,
                        node_kind=CompositionNodeKind.REFERENCE,
                        node_type=NODE_TYPE_ANSWER_ITEM,
                        content=None,
                        props=entry["props"],
                        schema_version=entry["schema_version"],
                        source_question_node_id=entry["source_question_node_id"],
                    )
                )
            else:
                c = entry["item"]
                child_nodes.append(
                    _new_node(
                        id=c.id,
                        parent_id=it.id,
                        slot=BODY_SLOT,
                        position=pos,
                        node_kind=c.node_kind,
                        node_type=c.node_type,
                        content=c.content,
                        props=c.props,
                        schema_version=c.schema_version,
                        anchor_before_node_id=c.anchor_before_node_id,
                    )
                )

    # 5) 应用:detach 旧节点 → 删旧行(子先父后,防自引用 FK)→ 建新(root 先 flush、子后)。
    for n in existing:
        db.expunge(n)
    await db.execute(
        delete(CompositionNode).where(
            CompositionNode.composition_id == comp.id,
            CompositionNode.parent_id.is_not(None),
        )
    )
    await db.execute(
        delete(CompositionNode).where(
            CompositionNode.composition_id == comp.id,
            CompositionNode.parent_id.is_(None),
        )
    )
    db.add_all(root_nodes)
    await db.flush()
    db.add_all(child_nodes)
    await db.flush()

    # 6) 与业务变更同事务写一条时间线事件。
    resolved_batch_id = batch_id or uuid.uuid4().hex
    await _add_event(
        db,
        composition_id=comp.id,
        composition_revision=new_revision,
        event_type="nodes_replaced",
        summary=f"Replaced nodes ({len(root_nodes)} root / {len(child_nodes)} child)",
        actor_id=actor.id,
        batch_id=resolved_batch_id,
        payload={"root": len(root_nodes), "child": len(child_nodes)},
    )

    await db.commit()
    refreshed = await crud_composition.composition.list_nodes(db, composition_id=comp.id)
    return new_revision, refreshed


# --------------------------------------------------------------------------- #
# Question node 版本状态 / 同步(冻结快照刷新)
# --------------------------------------------------------------------------- #
async def question_revision_status(
    db: AsyncSession,
    *,
    comp: Composition,
) -> List[Dict[str, Any]]:
    """基于稿件 question 节点批量查实时题目,只返回每 question_id 的当前 revision 与可用性。

    软删除 / 缺失题目视为 unavailable(current_revision 为 None);不返回任何题目内容。
    """
    nodes = await crud_composition.composition.list_nodes(db, composition_id=comp.id)
    unique_ids: List[int] = []
    seen: set[int] = set()
    for node in nodes:
        if node.node_type == NODE_TYPE_QUESTION and node.question_id is not None:
            if node.question_id not in seen:
                seen.add(node.question_id)
                unique_ids.append(node.question_id)
    if not unique_ids:
        return []

    result = await db.execute(
        select(Question.id, Question.content_revision, Question.deleted_at).where(
            Question.id.in_(unique_ids)
        )
    )
    rows = {row[0]: row for row in result.all()}

    statuses: List[Dict[str, Any]] = []
    for qid in unique_ids:
        row = rows.get(qid)
        if row is None or row[2] is not None:
            statuses.append({"question_id": qid, "current_revision": None, "available": False})
        else:
            statuses.append(
                {"question_id": qid, "current_revision": int(row[1] or 1), "available": True}
            )
    return statuses


async def sync_question_nodes(
    db: AsyncSession,
    *,
    comp: Composition,
    actor: User,
    expected_revision: int,
    node_ids: List[str],
) -> tuple[int, List[CompositionNode]]:
    """把指定 question 节点刷新为引用题目的最新冻结快照(一次事务,失败全回滚)。

    "同步此题" 与 "同步全部" 共用:前者传单个 id,后者传全部 question 节点 id。
    校验节点属于稿件且为 question 类型,并批量查同学科未软删的实时题目;
    组稿 revision 一次 +1,并写一条 question_nodes_synced 事件。
    """
    existing = await crud_composition.composition.list_nodes(db, composition_id=comp.id)
    existing_by_id = {n.id: n for n in existing}

    targets: List[CompositionNode] = []
    for nid in node_ids:
        node = existing_by_id.get(nid)
        if node is None:
            raise _not_found("Node")
        if node.node_type != NODE_TYPE_QUESTION:
            raise _unprocessable(f"node {nid} is not a question node")
        targets.append(node)

    question_ids = {n.question_id for n in targets if n.question_id is not None}
    result = await db.execute(
        select(Question).where(
            Question.id.in_(question_ids),
            Question.deleted_at.is_(None),
        )
    )
    questions_by_id = {q.id: q for q in result.scalars().all()}
    for node in targets:
        question = questions_by_id.get(node.question_id) if node.question_id else None
        if question is None:
            raise _unprocessable(f"question {node.question_id} not found or deleted")
        if question.subject_id != comp.subject_id:
            raise _unprocessable(
                f"question {node.question_id} belongs to a different subject"
            )

    new_revision = await _guarded_write(
        db,
        composition_id=comp.id,
        expected_revision=expected_revision,
        values={"updated_by": actor.id, "updated_at": datetime.utcnow()},
        require_deleted=False,
    )

    for node in targets:
        question = questions_by_id[node.question_id]
        node.content = _build_question_content_snapshot(question)
        node.question_revision = int(question.content_revision or 1)
        node.updated_by = actor.id
        db.add(node)

    await _add_event(
        db,
        composition_id=comp.id,
        composition_revision=new_revision,
        event_type="question_nodes_synced",
        summary=f"Synced {len(targets)} question node(s)",
        actor_id=actor.id,
        payload={"node_ids": list(node_ids), "synced": len(targets)},
    )

    await db.commit()
    refreshed = await crud_composition.composition.list_nodes(db, composition_id=comp.id)
    return new_revision, refreshed


# --------------------------------------------------------------------------- #
# 定稿 (Composition Version) —— 不可变 snapshot v2
# --------------------------------------------------------------------------- #
def _build_question_snapshot_from_node(node: CompositionNode) -> Dict[str, Any]:
    """从 question 节点冻结内容合成定稿题目投影;损坏/缺失快照 422(带 node id)。

    完全不查询实时 Question:id 取 node.question_id、revision 取 node.question_revision,
    其余字段来自 node.content(QuestionContentSnapshot)。
    """
    content = node.content
    if not isinstance(content, dict):
        raise _unprocessable(f"question node {node.id} has no frozen content")
    try:
        snapshot = QuestionSnapshot(
            id=node.question_id,
            content_revision=node.question_revision,
            **content,
        )
    except (ValidationError, TypeError) as exc:
        raise _unprocessable(f"question node {node.id} has a corrupt snapshot") from exc
    return snapshot.model_dump()


def _node_snapshot(node: CompositionNode) -> Dict[str, Any]:
    """把单个规范化节点冻结为 snapshot 投影(保留完整结构 + 配置)。"""
    kind = node.node_kind.value if isinstance(node.node_kind, CompositionNodeKind) else node.node_kind
    snap: Dict[str, Any] = {
        "id": node.id,
        "parent_id": node.parent_id,
        "slot": node.slot,
        "position": node.position,
        "node_kind": kind,
        "node_type": node.node_type,
        "schema_version": node.schema_version,
    }
    nt = node.node_type
    if nt == NODE_TYPE_RICH_TEXT:
        snap["content"] = node.content
    elif nt == NODE_TYPE_HEADING:
        snap["content"] = node.content
        snap["props"] = node.props
    elif nt == NODE_TYPE_QUESTION:
        snap["question_id"] = node.question_id
        snap["question_revision"] = node.question_revision
        snap["question"] = _build_question_snapshot_from_node(node)
    elif nt == NODE_TYPE_QUESTION_DETAILS:
        snap["props"] = node.props
    elif nt == NODE_TYPE_ANSWER_ITEM:
        snap["source_question_node_id"] = node.source_question_node_id
        snap["props"] = node.props
    if node.anchor_before_node_id is not None:
        snap["anchor_before_node_id"] = node.anchor_before_node_id
    return snap


def _ordered_nodes(nodes: List[CompositionNode]) -> List[CompositionNode]:
    """按文档前序(root 按 position;module 子节点紧随其后按 position)展平。"""
    roots = sorted(
        [n for n in nodes if n.parent_id is None], key=lambda n: (n.position, n.id)
    )
    children_by_parent: Dict[str, List[CompositionNode]] = defaultdict(list)
    for n in nodes:
        if n.parent_id is not None:
            children_by_parent[n.parent_id].append(n)
    ordered: List[CompositionNode] = []
    for root in roots:
        ordered.append(root)
        for child in sorted(children_by_parent.get(root.id, []), key=lambda n: (n.position, n.id)):
            ordered.append(child)
    return ordered


def _build_snapshot(
    comp: Composition,
    nodes: List[CompositionNode],
    finalized_at: datetime,
) -> Dict[str, Any]:
    """组装 snapshot v2:顶层元数据 + 前序展平的规范化节点。

    question 节点携带冻结题目投影;answer_item 保留配置(included/overrides + source),
    可由同 snapshot 内 source question 节点解析出答案,定稿完全不查询实时题库。
    """
    ordered = _ordered_nodes(nodes)
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "composition_id": comp.id,
        "source_revision": comp.revision,
        "title": comp.title,
        "subject_id": comp.subject_id,
        "finalized_at": finalized_at.isoformat(),
        "nodes": [_node_snapshot(n) for n in ordered],
    }


async def finalize_version(
    db: AsyncSession,
    *,
    comp: Composition,
    actor: User,
    expected_revision: int,
    label: Optional[str] = None,
) -> CompositionVersion:
    """把当前 composition 冻结为不可变版本。

    - 软删除稿不允许新定稿(409);expected_revision 必须匹配当前 revision(409)。
    - 定稿不修改 composition.revision;同一 revision 允许重复定稿,version_no 单调递增。
    - 版本 + 一条 finalized 事件同事务写入;version_no 用 MAX+1,并发碰撞由 unique 约束
      拦截,局部安全重试一次后仍冲突则 409。
    """
    if comp.deleted_at is not None:
        raise _conflict("Cannot finalize a deleted composition")
    if comp.revision != expected_revision:
        raise _conflict("Composition revision mismatch")

    nodes = await crud_composition.composition.list_nodes(db, composition_id=comp.id)
    finalized_at = datetime.utcnow()
    snapshot = _build_snapshot(comp, nodes, finalized_at)

    comp_id = comp.id
    comp_revision = comp.revision
    comp_title = comp.title
    comp_subject_id = comp.subject_id

    for attempt in range(2):
        version_no = await crud_composition.composition.max_version_no(
            db, composition_id=comp_id
        ) + 1
        version = CompositionVersion(
            composition_id=comp_id,
            version_no=version_no,
            source_revision=comp_revision,
            title=comp_title,
            subject_id=comp_subject_id,
            snapshot=snapshot,
            label=label,
            finalized_at=finalized_at,
            finalized_by=actor.id,
        )
        db.add(version)
        await _add_event(
            db,
            composition_id=comp_id,
            composition_revision=comp_revision,
            event_type="finalized",
            summary=f"Finalized version {version_no}",
            actor_id=actor.id,
            target_type="version",
            target_id=str(version_no),
            payload={"version_no": version_no, "label": label},
        )
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            if attempt == 0:
                continue
            raise _conflict("Version number conflict")
        await db.refresh(version)
        return version

    # 不可达:循环内要么 return 要么在末次 raise。
    raise _conflict("Version number conflict")
