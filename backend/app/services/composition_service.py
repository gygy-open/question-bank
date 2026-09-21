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
载体是 `app.capabilities.errors` 的 DomainError,不是 HTTPException —— 同一套逻辑
要能被 AI 工具与 worker 调用;状态码由 app.main 的 exception handler 映射。
"""
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid

from pydantic import ValidationError
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.capabilities.errors import Conflict, Invalid, NotFound, Unprocessable
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
    NODE_TYPE_ANSWER_SPACE,
    NODE_TYPE_HEADING,
    NODE_TYPE_QUESTION,
    NODE_TYPE_QUESTION_DETAILS,
    NODE_TYPE_QUESTION_GROUP,
    NODE_TYPE_RICH_TEXT,
    ScopeType,
)
from app.models.question import Question, QuestionType, QuestionVisibility
from app.models.question_group import QuestionGroup, QuestionGroupItem, Stimulus
from app.models.user import User
from app.schemas.composition import (
    ANSWER_FIELD_KEYS,
    CompositionNodeInput,
    QuestionContentSnapshot,
    QuestionSnapshot,
)
from app.services.question_content import parse_json_field

SNAPSHOT_SCHEMA_VERSION = 3


# --------------------------------------------------------------------------- #
# 内部工具
# --------------------------------------------------------------------------- #
def _not_found(what: str) -> NotFound:
    return NotFound(f"{what} not found")


def _conflict(detail: str) -> Conflict:
    return Conflict(detail)


def _bad_request(detail: str) -> Invalid:
    return Invalid(detail)


def _unprocessable(detail: str) -> Unprocessable:
    return Unprocessable(detail)


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
    numbering_enabled: bool = False,
    commit: bool = True,
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
        numbering_enabled=numbering_enabled,
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
    if commit:
        await db.commit()
    await db.refresh(comp)
    return comp


async def duplicate_composition(
    db: AsyncSession,
    *,
    source: Composition,
    actor: User,
) -> Composition:
    """整份克隆:新建"标题 副本"稿件,原样复制全部节点(id 重生成,question 快照原样保留、不重新冻结)。

    与 replace_nodes 不同,此处直接搬运源节点的 content/question_revision,不去读实时题目,
    避免"复制"时静默把过期题目一并同步成最新版本。
    """
    new_comp = await create_composition(
        db,
        subject_id=source.subject_id,
        scope_type=source.scope_type,
        owner_id=source.owner_id,
        actor=actor,
        title=f"{source.title} 副本",
        description=source.description,
        folder_id=source.folder_id,
    )

    if source.numbering_enabled or source.scoring_enabled or source.question_display:
        new_comp = await update_composition(
            db,
            comp=new_comp,
            actor=actor,
            expected_revision=new_comp.revision,
            numbering_enabled=source.numbering_enabled,
            scoring_enabled=source.scoring_enabled,
            question_display=source.question_display,
        )

    source_nodes = await crud_composition.composition.list_nodes(db, composition_id=source.id)
    if source_nodes:
        id_map = {n.id: str(uuid.uuid4()) for n in source_nodes}

        def _clone(n: CompositionNode) -> CompositionNode:
            return CompositionNode(
                id=id_map[n.id],
                composition_id=new_comp.id,
                parent_id=id_map.get(n.parent_id),
                slot=n.slot,
                position=n.position,
                node_kind=n.node_kind,
                node_type=n.node_type,
                content=n.content,
                props=n.props,
                schema_version=n.schema_version,
                question_id=n.question_id,
                question_revision=n.question_revision,
                question_group_id=n.question_group_id,
                question_group_revision=n.question_group_revision,
                stimulus_id=n.stimulus_id,
                stimulus_revision=n.stimulus_revision,
                source_question_node_id=id_map.get(n.source_question_node_id),
                anchor_before_node_id=id_map.get(n.anchor_before_node_id),
                created_by=actor.id,
                updated_by=actor.id,
            )

        # root 先、module 子后插入,满足自引用 FK(与 replace_nodes 的删旧建新顺序一致)。
        roots = [n for n in source_nodes if n.parent_id is None]
        children = [n for n in source_nodes if n.parent_id is not None]
        db.add_all(_clone(n) for n in roots)
        await db.flush()
        db.add_all(_clone(n) for n in children)
        await db.flush()

    await _add_event(
        db,
        composition_id=new_comp.id,
        composition_revision=new_comp.revision,
        event_type="duplicated",
        summary=f"Duplicated from composition #{source.id}",
        actor_id=actor.id,
    )
    await db.commit()
    refreshed = await crud_composition.composition.get_scoped(
        db,
        composition_id=new_comp.id,
        subject_id=new_comp.subject_id,
        scope_type=new_comp.scope_type,
        owner_id=new_comp.owner_id,
    )
    assert refreshed is not None
    return refreshed


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
    numbering_enabled: Optional[bool] = None,
    scoring_enabled: Optional[bool] = None,
    question_display: Optional[Dict[str, bool]] = None,
) -> Composition:
    values: dict = {"updated_by": actor.id, "updated_at": datetime.utcnow()}
    moved = False
    if title is not None:
        values["title"] = title
    if description is not None:
        values["description"] = description
    if status_value is not None:
        values["status"] = status_value
    if numbering_enabled is not None:
        values["numbering_enabled"] = numbering_enabled
    # 赋分依赖题号:开启赋分要求(生效后的)题号为真;题号被关闭时级联关闭赋分。
    effective_numbering = numbering_enabled if numbering_enabled is not None else comp.numbering_enabled
    if scoring_enabled:
        if not effective_numbering:
            raise _bad_request("scoring_enabled requires numbering_enabled")
        values["scoring_enabled"] = True
    elif scoring_enabled is False:
        values["scoring_enabled"] = False
    elif not effective_numbering and comp.scoring_enabled:
        values["scoring_enabled"] = False
    if question_display is not None:
        values["question_display"] = {
            k: bool(question_display.get(k, False)) for k in ANSWER_FIELD_KEYS
        }
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
    scope_type: ScopeType,
) -> Question:
    """校验 question 节点引用并返回实时题目。

    缺失 / 软删除 / 跨学科统一 422(不信任客户端传入的 revision/快照)。
    私有题禁止进入共享(shared)组稿:快照会冻结题面,泄漏私有内容。
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
    if scope_type == ScopeType.SHARED and question.visibility == QuestionVisibility.PRIVATE.value:
        raise _unprocessable(f"private question {question_id} cannot be added to a shared composition")
    return question


async def _load_scoped_question_group(
    db: AsyncSession,
    *,
    question_group_id: int,
    subject_id: int,
    scope_type: ScopeType,
    actor: User,
) -> QuestionGroup:
    result = await db.execute(
        select(QuestionGroup)
        .options(
            selectinload(QuestionGroup.stimulus),
            selectinload(QuestionGroup.items).selectinload(QuestionGroupItem.question),
        )
        .where(
            QuestionGroup.id == question_group_id,
            QuestionGroup.deleted_at.is_(None),
        )
    )
    group = result.scalar_one_or_none()
    if group is None or group.subject_id != subject_id:
        raise _unprocessable(f"question group {question_group_id} not found or belongs to a different subject")
    if (
        group.visibility == QuestionVisibility.PRIVATE.value
        and not actor.is_superuser
        and group.created_by != actor.id
    ):
        raise _unprocessable(f"question group {question_group_id} is not accessible")
    stimulus = group.stimulus
    if stimulus is None or stimulus.deleted_at is not None:
        raise _unprocessable(f"question group {question_group_id} stimulus is unavailable")
    questions = [item.question for item in group.items]
    if any(question is None or question.deleted_at is not None for question in questions):
        raise _unprocessable(f"question group {question_group_id} contains unavailable questions")
    if scope_type == ScopeType.SHARED and (
        group.visibility == QuestionVisibility.PRIVATE.value
        or stimulus.visibility == QuestionVisibility.PRIVATE.value
        or any(q.visibility == QuestionVisibility.PRIVATE.value for q in questions)
    ):
        raise _unprocessable(
            f"private question group {question_group_id} cannot be added to a shared composition"
        )
    return group


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
    children_by_parent: Dict[str, List[CompositionNodeInput]] = defaultdict(list)
    for it in items:
        if it.parent_id is not None:
            children_by_parent[it.parent_id].append(it)

    for it in items:
        if it.parent_id is not None:
            parent = by_id.get(it.parent_id)
            if parent is None:
                raise _bad_request(f"node {it.id} references a missing parent")
            if parent.node_type not in (NODE_TYPE_QUESTION_DETAILS, NODE_TYPE_QUESTION_GROUP):
                raise _bad_request(
                    f"node {it.id} parent must be a supported module"
                )
            allowed = (
                {NODE_TYPE_ANSWER_ITEM, NODE_TYPE_HEADING, NODE_TYPE_RICH_TEXT}
                if parent.node_type == NODE_TYPE_QUESTION_DETAILS
                else {
                    NODE_TYPE_QUESTION,
                    NODE_TYPE_ANSWER_SPACE,
                    NODE_TYPE_HEADING,
                    NODE_TYPE_RICH_TEXT,
                }
            )
            if it.node_type not in allowed:
                raise _bad_request(f"node {it.id} is not valid inside {parent.node_type}")
        if it.node_type == NODE_TYPE_ANSWER_ITEM:
            src = by_id.get(it.source_question_node_id)
            parent = by_id.get(src.parent_id) if src is not None and src.parent_id else None
            if (
                src is None
                or src.node_type != NODE_TYPE_QUESTION
                or (src.parent_id is not None and (
                    parent is None or parent.node_type != NODE_TYPE_QUESTION_GROUP
                ))
            ):
                raise _bad_request(
                    f"answer_item {it.id} source must point to an answerable question node"
                )
        if it.anchor_before_node_id is not None:
            target = by_id.get(it.anchor_before_node_id)
            anchor_parent = by_id.get(it.parent_id) if it.parent_id is not None else None
            # 锚点目标是所在 module 的“可排序主体”:详情模块为 answer_item,题组为小题。
            expected = (
                NODE_TYPE_QUESTION
                if anchor_parent is not None
                and anchor_parent.node_type == NODE_TYPE_QUESTION_GROUP
                else NODE_TYPE_ANSWER_ITEM
            )
            if (
                target is None
                or target.node_type != expected
                or target.parent_id != it.parent_id
            ):
                raise _bad_request(
                    f"node {it.id} anchor must point to a {expected} in the same module"
                )

    for parent_id, children in children_by_parent.items():
        parent = by_id[parent_id]
        if parent.node_type != NODE_TYPE_QUESTION_GROUP:
            continue
        previous_question_id: Optional[str] = None
        for child in children:
            # 自定义说明块由规范化统一重排,不参与作答区相邻性判定。
            if child.node_type in (NODE_TYPE_HEADING, NODE_TYPE_RICH_TEXT):
                continue
            if child.node_type == NODE_TYPE_QUESTION:
                previous_question_id = child.id
            elif child.source_question_node_id != previous_question_id:
                raise _bad_request(
                    f"answer_space {child.id} must immediately follow and reference its question"
                )
            else:
                previous_question_id = None


def _normalize_module_children(
    module: CompositionNodeInput,
    *,
    answerable_questions: List[tuple[Any, int]],
    module_root_index: int,
    children: List[CompositionNodeInput],
) -> List[Dict[str, Any]]:
    """按 module scope 规范化 question_details 的子节点顺序与 answer_item 集合。

        - scope=all → 整稿全部可作答 question(root + question_group child);
            scope=before → 所在 root module 位于当前 module 之前的。
    - 每个范围内 question 节点产出一条 answer_item(重复 question_id 因节点不同而各自保留)。
    - answer_item 相对顺序跟随正文(题序)。
    - 尽量复用客户端传入的 answer_item(按 source_question_node_id 顺序消费)以保留
      id / included / overrides;不足则服务端生成新 UUID + 默认 props。
    - 自定义 heading/rich_text 按 anchor_before_node_id 混排;未锚定者按其相对首个 answer_item
      的位置置顶(leading)或置尾(trailing),悬空锚点同此规则(保序)。

    返回子节点规范化描述列表(dict),position 由列表下标决定。
    """
    scope = (module.props or {}).get("scope")
    if scope == "all":
        scoped_questions = [question for question, _ in answerable_questions]
    else:  # before
        scoped_questions = [
            question for question, root_index in answerable_questions
            if root_index < module_root_index
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
    # 未锚定的自定义节点:位于首个 answer_item 之前 → 置顶(leading),之后 → 置尾(trailing)。
    anchored: Dict[str, List[CompositionNodeInput]] = defaultdict(list)
    leading: List[CompositionNodeInput] = []
    trailing: List[CompositionNodeInput] = []
    seen_answer_item = False
    for c in children:
        if c.node_type == NODE_TYPE_ANSWER_ITEM:
            seen_answer_item = True
            continue
        if c.node_type not in (NODE_TYPE_HEADING, NODE_TYPE_RICH_TEXT):
            continue
        if c.anchor_before_node_id in final_ai_ids:
            anchored[c.anchor_before_node_id].append(c)
        elif not seen_answer_item:
            leading.append(c)
        else:
            trailing.append(c)

    ordered: List[Dict[str, Any]] = []
    for c in leading:
        ordered.append({"kind": "custom", "item": c})
    for ai in answer_items:
        for c in anchored.get(ai["id"], []):
            ordered.append({"kind": "custom", "item": c})
        ordered.append({"kind": "answer_item", **ai})
    for c in trailing:
        ordered.append({"kind": "custom", "item": c})
    return ordered


def _normalize_question_group_children(
    children: List[CompositionNodeInput],
) -> List[Dict[str, Any]]:
    """规范化 question_group 子节点顺序,使版面结构与相邻性不变量由服务端保证。

    - 小题顺序跟随题组成员顺序(调用方已校验客户端未改动它)。
    - 作答区按 source_question_node_id 紧跟其小题,与客户端传入位置无关。
    - 自定义 heading/rich_text 按 anchor_before_node_id 排在目标小题之前;
      未锚定者按其相对首道小题的位置置顶(材料之后、首题之前)或置尾,悬空锚点同此规则。

    返回子节点规范化描述列表(dict),position 由列表下标决定。
    """
    questions = [c for c in children if c.node_type == NODE_TYPE_QUESTION]
    question_ids = {c.id for c in questions}
    answer_space_by_source = {
        c.source_question_node_id: c
        for c in children
        if c.node_type == NODE_TYPE_ANSWER_SPACE
    }

    anchored: Dict[str, List[CompositionNodeInput]] = defaultdict(list)
    leading: List[CompositionNodeInput] = []
    trailing: List[CompositionNodeInput] = []
    seen_question = False
    for c in children:
        if c.node_type == NODE_TYPE_QUESTION:
            seen_question = True
            continue
        if c.node_type not in (NODE_TYPE_HEADING, NODE_TYPE_RICH_TEXT):
            continue
        if c.anchor_before_node_id in question_ids:
            anchored[c.anchor_before_node_id].append(c)
        elif not seen_question:
            leading.append(c)
        else:
            trailing.append(c)

    ordered: List[Dict[str, Any]] = []
    for c in leading:
        ordered.append({"kind": "custom", "item": c})
    for q in questions:
        for c in anchored.get(q.id, []):
            ordered.append({"kind": "custom", "item": c})
        ordered.append({"kind": "question", "item": q})
        space = answer_space_by_source.get(q.id)
        if space is not None:
            ordered.append({"kind": "answer_space", "item": space})
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
    commit: bool = True,
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

    children_by_parent: Dict[str, List[CompositionNodeInput]] = defaultdict(list)
    for it in items:
        if it.parent_id is not None:
            children_by_parent[it.parent_id].append(it)

    group_plan: Dict[str, Dict[str, Any]] = {}
    for it in items:
        if it.node_type != NODE_TYPE_QUESTION_GROUP:
            continue
        assert it.question_group_id is not None
        previous = existing_by_id.get(it.id)
        requested_children = children_by_parent.get(it.id, [])
        if previous is not None and previous.node_type == NODE_TYPE_QUESTION_GROUP:
            if previous.question_group_id != it.question_group_id:
                raise _bad_request("an existing question_group node cannot change its source")
            previous_children = sorted(
                (node for node in existing if node.parent_id == it.id),
                key=lambda node: node.position,
            )
            previous_questions = [
                node for node in previous_children if node.node_type == NODE_TYPE_QUESTION
            ]
            requested_questions = [
                node for node in requested_children if node.node_type == NODE_TYPE_QUESTION
            ]
            if [node.question_id for node in requested_questions] != [
                node.question_id for node in previous_questions
            ]:
                raise _bad_request(
                    "an existing question_group node cannot change member question order"
                )
            group_plan[it.id] = {
                "previous": previous,
                "questions": previous_questions,
                "children": requested_children,
            }
        else:
            if requested_children:
                raise _bad_request("a new question_group node must not provide children")
            group = await _load_scoped_question_group(
                db,
                question_group_id=it.question_group_id,
                subject_id=comp.subject_id,
                scope_type=comp.scope_type,
                actor=actor,
            )
            group_plan[it.id] = {"group": group}

    # 2) 冻结 question 快照计划:新建 / question_id 变化 → 读实时题目;否则保留 DB 快照。
    question_plan: Dict[str, Optional[tuple[int, Dict[str, Any]]]] = {}
    for it in items:
        if it.node_type != NODE_TYPE_QUESTION or it.parent_id is not None:
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
                db, question_id=it.question_id, subject_id=comp.subject_id,
                scope_type=comp.scope_type,
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
                    props=it.props,
                    schema_version=it.schema_version,
                    question_id=it.question_id,
                    question_revision=revision,
                )
            )
        elif it.node_type == NODE_TYPE_QUESTION_GROUP:
            plan = group_plan[it.id]
            previous = plan.get("previous")
            group = plan.get("group")
            root_nodes.append(
                _new_node(
                    id=it.id,
                    parent_id=None,
                    slot=None,
                    position=root_idx,
                    node_kind=CompositionNodeKind.MODULE,
                    node_type=NODE_TYPE_QUESTION_GROUP,
                    content=(
                        previous.content
                        if previous is not None
                        else parse_json_field(group.stimulus.content)
                    ),
                    props=None,
                    schema_version=it.schema_version,
                    question_group_id=it.question_group_id,
                    question_group_revision=(
                        previous.question_group_revision
                        if previous is not None
                        else int(group.revision or 1)
                    ),
                    stimulus_id=(previous.stimulus_id if previous is not None else group.stimulus_id),
                    stimulus_revision=(
                        previous.stimulus_revision
                        if previous is not None
                        else int(group.stimulus.revision or 1)
                    ),
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
        if it.node_type != NODE_TYPE_QUESTION_GROUP:
            continue
        plan = group_plan[it.id]
        previous_questions = plan.get("questions")
        if previous_questions is None:
            group = plan["group"]
            for pos, group_item in enumerate(group.items):
                question = group_item.question
                child_nodes.append(
                    _new_node(
                        id=str(uuid.uuid4()),
                        parent_id=it.id,
                        slot=BODY_SLOT,
                        position=pos,
                        node_kind=CompositionNodeKind.BLOCK,
                        node_type=NODE_TYPE_QUESTION,
                        content=_build_question_content_snapshot(question),
                        props=None,
                        schema_version=1,
                        question_id=question.id,
                        question_revision=int(question.content_revision or 1),
                    )
                )
        else:
            question_index = 0
            for pos, entry in enumerate(
                _normalize_question_group_children(plan["children"])
            ):
                child = entry["item"]
                if entry["kind"] == "question":
                    previous_question = previous_questions[question_index]
                    question_index += 1
                    child_nodes.append(
                        _new_node(
                            id=child.id,
                            parent_id=it.id,
                            slot=BODY_SLOT,
                            position=pos,
                            node_kind=CompositionNodeKind.BLOCK,
                            node_type=NODE_TYPE_QUESTION,
                            content=previous_question.content,
                            props=child.props,
                            schema_version=child.schema_version,
                            question_id=previous_question.question_id,
                            question_revision=previous_question.question_revision,
                        )
                    )
                elif entry["kind"] == "answer_space":
                    child_nodes.append(
                        _new_node(
                            id=child.id,
                            parent_id=it.id,
                            slot=BODY_SLOT,
                            position=pos,
                            node_kind=CompositionNodeKind.BLOCK,
                            node_type=NODE_TYPE_ANSWER_SPACE,
                            content=None,
                            props=child.props,
                            schema_version=child.schema_version,
                            source_question_node_id=child.source_question_node_id,
                        )
                    )
                else:
                    child_nodes.append(
                        _new_node(
                            id=child.id,
                            parent_id=it.id,
                            slot=BODY_SLOT,
                            position=pos,
                            node_kind=child.node_kind,
                            node_type=child.node_type,
                            content=child.content,
                            props=child.props,
                            schema_version=child.schema_version,
                            anchor_before_node_id=child.anchor_before_node_id,
                        )
                    )

    answerable_questions: List[tuple[Any, int]] = []
    for root in root_nodes:
        if root.node_type == NODE_TYPE_QUESTION:
            answerable_questions.append((root, root.position))
        elif root.node_type == NODE_TYPE_QUESTION_GROUP:
            answerable_questions.extend(
                (child, root.position)
                for child in child_nodes
                if child.parent_id == root.id and child.node_type == NODE_TYPE_QUESTION
            )

    for it in root_items:
        if it.node_type != NODE_TYPE_QUESTION_DETAILS:
            continue
        ordered = _normalize_module_children(
            it,
            answerable_questions=answerable_questions,
            module_root_index=root_index_by_id[it.id],
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

    if commit:
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
        select(
            Question.id,
            Question.content_revision,
            Question.deleted_at,
            Question.subject_id,
            Question.visibility,
        ).where(Question.id.in_(unique_ids))
    )
    rows = {row[0]: row for row in result.all()}

    statuses: List[Dict[str, Any]] = []
    for qid in unique_ids:
        row = rows.get(qid)
        unavailable = (
            row is None
            or row[2] is not None
            or row[3] != comp.subject_id
            or (
                comp.scope_type == ScopeType.SHARED
                and row[4] == QuestionVisibility.PRIVATE.value
            )
        )
        if unavailable:
            statuses.append({"question_id": qid, "current_revision": None, "available": False})
        else:
            statuses.append(
                {"question_id": qid, "current_revision": int(row[1] or 1), "available": True}
            )
    return statuses


async def question_group_revision_status(
    db: AsyncSession,
    *,
    comp: Composition,
    actor: User,
) -> List[Dict[str, Any]]:
    """返回题组节点的实时来源状态；不可见来源统一收敛为 unavailable。"""
    nodes = await crud_composition.composition.list_nodes(db, composition_id=comp.id)
    group_nodes = [node for node in nodes if node.node_type == NODE_TYPE_QUESTION_GROUP]
    if not group_nodes:
        return []

    result = await db.execute(
        select(QuestionGroup)
        .options(
            selectinload(QuestionGroup.stimulus),
            selectinload(QuestionGroup.items).selectinload(QuestionGroupItem.question),
        )
        .where(
            QuestionGroup.id.in_(
                {node.question_group_id for node in group_nodes}
            )
        )
    )
    groups_by_id = {group.id: group for group in result.scalars().unique().all()}
    children_by_parent: Dict[str, List[CompositionNode]] = defaultdict(list)
    for child in nodes:
        if child.parent_id is not None:
            children_by_parent[child.parent_id].append(child)
    pinned_question_ids = {
        child.question_id
        for node in group_nodes
        for child in children_by_parent[node.id]
        if child.node_type == NODE_TYPE_QUESTION
    }
    question_result = await db.execute(
        select(Question).where(Question.id.in_(pinned_question_ids))
    )
    questions_by_id = {
        question.id: question for question in question_result.scalars().all()
    }

    statuses: List[Dict[str, Any]] = []
    for node in group_nodes:
        pinned_members = [
            child
            for child in sorted(children_by_parent[node.id], key=lambda item: item.position)
            if child.node_type == NODE_TYPE_QUESTION
        ]
        group = groups_by_id.get(node.question_group_id)
        group_available = bool(
            group is not None
            and group.deleted_at is None
            and group.subject_id == comp.subject_id
            and (
                group.visibility != QuestionVisibility.PRIVATE.value
                or (
                    comp.scope_type == ScopeType.PERSONAL
                    and (actor.is_superuser or group.created_by == actor.id)
                )
            )
        )
        if not group_available:
            statuses.append({
                "node_id": node.id,
                "question_group_id": node.question_group_id,
                "pinned_revision": node.question_group_revision,
                "current_revision": None,
                "stimulus_pinned_revision": node.stimulus_revision,
                "stimulus_current_revision": None,
                "members": [{
                    "node_id": child.id,
                    "question_id": child.question_id,
                    "pinned_revision": child.question_revision,
                    "current_revision": None,
                    "available": False,
                } for child in pinned_members],
                "group_available": False,
                "stimulus_available": False,
                "structure_changed": False,
                "stale": True,
            })
            continue

        stimulus = group.stimulus
        stimulus_available = bool(
            stimulus is not None
            and stimulus.deleted_at is None
            and stimulus.subject_id == comp.subject_id
            and not (
                comp.scope_type == ScopeType.SHARED
                and stimulus.visibility == QuestionVisibility.PRIVATE.value
            )
        )
        current_items = sorted(group.items, key=lambda item: item.position)
        member_statuses: List[Dict[str, Any]] = []
        for child in pinned_members:
            question = questions_by_id.get(child.question_id)
            available = bool(
                question is not None
                and question.deleted_at is None
                and question.subject_id == comp.subject_id
                and not (
                    comp.scope_type == ScopeType.SHARED
                    and question.visibility == QuestionVisibility.PRIVATE.value
                )
            )
            member_statuses.append({
                "node_id": child.id,
                "question_id": child.question_id,
                "pinned_revision": child.question_revision,
                "current_revision": int(question.content_revision or 1) if available else None,
                "available": available,
            })
        current_member_ids = [item.question_id for item in current_items]
        pinned_member_ids = [child.question_id for child in pinned_members]
        structure_changed = current_member_ids != pinned_member_ids
        stale = (
            node.question_group_revision != int(group.revision or 1)
            or not stimulus_available
            or node.stimulus_revision != int(stimulus.revision or 1)
            or structure_changed
            or any(
                not member["available"]
                or member["pinned_revision"] != member["current_revision"]
                for member in member_statuses
            )
        )
        statuses.append({
            "node_id": node.id,
            "question_group_id": node.question_group_id,
            "pinned_revision": node.question_group_revision,
            "current_revision": int(group.revision or 1),
            "stimulus_pinned_revision": node.stimulus_revision,
            "stimulus_current_revision": int(stimulus.revision or 1) if stimulus_available else None,
            "members": member_statuses,
            "group_available": True,
            "stimulus_available": stimulus_available,
            "structure_changed": structure_changed,
            "stale": stale,
        })
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
        if node.parent_id is not None:
            raise _unprocessable(
                f"question node {nid} belongs to a question group and must be synced with its group"
            )
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


async def sync_question_group_nodes(
    db: AsyncSession,
    *,
    comp: Composition,
    actor: User,
    expected_revision: int,
    node_ids: List[str],
) -> tuple[int, List[CompositionNode]]:
    """原子刷新指定题组节点的来源快照、成员顺序及成员题目快照。"""
    existing = await crud_composition.composition.list_nodes(db, composition_id=comp.id)
    existing_by_id = {node.id: node for node in existing}
    children_by_parent: Dict[str, List[CompositionNode]] = defaultdict(list)
    for child in existing:
        if child.parent_id is not None:
            children_by_parent[child.parent_id].append(child)

    plans: List[Dict[str, Any]] = []
    for node_id in node_ids:
        node = existing_by_id.get(node_id)
        if node is None:
            raise _not_found("Node")
        if node.node_type != NODE_TYPE_QUESTION_GROUP:
            raise _unprocessable(f"node {node_id} is not a question_group node")
        group = await _load_scoped_question_group(
            db,
            question_group_id=node.question_group_id,
            subject_id=comp.subject_id,
            scope_type=comp.scope_type,
            actor=actor,
        )
        old_children = sorted(children_by_parent[node.id], key=lambda child: child.position)
        old_questions = [
            child for child in old_children if child.node_type == NODE_TYPE_QUESTION
        ]
        old_questions_by_id = {child.question_id: child for child in old_questions}
        answer_spaces_by_source = {
            child.source_question_node_id: child
            for child in old_children
            if child.node_type == NODE_TYPE_ANSWER_SPACE
        }
        # 用户在稿件内插入的说明块:记录其相对首道小题的位置,刷新时据此回落。
        old_customs: List[Dict[str, Any]] = []
        seen_question = False
        for child in old_children:
            if child.node_type == NODE_TYPE_QUESTION:
                seen_question = True
                continue
            if child.node_type not in (NODE_TYPE_HEADING, NODE_TYPE_RICH_TEXT):
                continue
            old_customs.append({"node": child, "after_first_question": seen_question})
        old_question_ids = [child.question_id for child in old_questions]
        new_question_ids = [item.question_id for item in group.items]
        old_set = set(old_question_ids)
        new_set = set(new_question_ids)
        common = old_set & new_set
        plans.append({
            "node": node,
            "group": group,
            "old_children": old_children,
            "old_questions": old_questions,
            "old_questions_by_id": old_questions_by_id,
            "answer_spaces_by_source": answer_spaces_by_source,
            "old_customs": old_customs,
            "added": [question_id for question_id in new_question_ids if question_id not in old_set],
            "removed": [question_id for question_id in old_question_ids if question_id not in new_set],
            "reordered": (
                [question_id for question_id in old_question_ids if question_id in common]
                != [question_id for question_id in new_question_ids if question_id in common]
            ),
            "old_group_revision": node.question_group_revision,
        })

    new_revision = await _guarded_write(
        db,
        composition_id=comp.id,
        expected_revision=expected_revision,
        values={"updated_by": actor.id, "updated_at": datetime.utcnow()},
        require_deleted=False,
    )

    target_ids = [plan["node"].id for plan in plans]
    for plan in plans:
        for child in plan["old_children"]:
            db.expunge(child)
    await db.execute(
        delete(CompositionNode).where(
            CompositionNode.composition_id == comp.id,
            CompositionNode.parent_id.in_(target_ids),
        )
    )

    new_children: List[CompositionNode] = []
    event_groups: List[Dict[str, Any]] = []
    for plan in plans:
        node = plan["node"]
        group = plan["group"]
        node.content = parse_json_field(group.stimulus.content)
        node.question_group_revision = int(group.revision or 1)
        node.stimulus_id = group.stimulus_id
        node.stimulus_revision = int(group.stimulus.revision or 1)
        node.updated_by = actor.id
        db.add(node)

        position = 0
        ordered_items = sorted(group.items, key=lambda item: item.position)
        # 小题节点 ID 先定下来,自定义块才能把锚点重指到刷新后的节点上。
        node_id_by_question_id: Dict[int, str] = {}
        for group_item in ordered_items:
            previous = plan["old_questions_by_id"].get(group_item.question_id)
            node_id_by_question_id[group_item.question_id] = (
                previous.id if previous is not None else str(uuid.uuid4())
            )

        old_question_order = [child.question_id for child in plan["old_questions"]]
        old_question_id_by_node_id = {
            child.id: child.question_id for child in plan["old_questions"]
        }

        def _resolve_anchor(anchor_node_id: Optional[str]) -> Optional[str]:
            """锚点题被移除时顺延到其后第一道仍存在的小题,保持"排在它之前"的相对位置。"""
            question_id = old_question_id_by_node_id.get(anchor_node_id)
            if question_id is None or question_id not in old_question_order:
                return None
            start = old_question_order.index(question_id)
            for candidate in old_question_order[start:]:
                if candidate in node_id_by_question_id:
                    return node_id_by_question_id[candidate]
            return None

        anchored_customs: Dict[str, List[Any]] = defaultdict(list)
        leading_customs: List[Any] = []
        trailing_customs: List[Any] = []
        for entry in plan["old_customs"]:
            child = entry["node"]
            target = _resolve_anchor(child.anchor_before_node_id)
            if target is not None:
                anchored_customs[target].append(child)
            elif entry["after_first_question"]:
                trailing_customs.append(child)
            else:
                leading_customs.append(child)

        def _emit_custom(child: Any, anchor: Optional[str]) -> None:
            nonlocal position
            new_children.append(
                CompositionNode(
                    id=child.id,
                    composition_id=comp.id,
                    parent_id=node.id,
                    slot=BODY_SLOT,
                    position=position,
                    node_kind=child.node_kind,
                    node_type=child.node_type,
                    content=child.content,
                    props=child.props,
                    schema_version=child.schema_version,
                    anchor_before_node_id=anchor,
                    created_by=actor.id,
                    updated_by=actor.id,
                )
            )
            position += 1

        for child in leading_customs:
            _emit_custom(child, None)

        for group_item in ordered_items:
            question = group_item.question
            previous = plan["old_questions_by_id"].get(question.id)
            question_node_id = node_id_by_question_id[question.id]
            for child in anchored_customs.get(question_node_id, []):
                _emit_custom(child, question_node_id)
            new_children.append(
                CompositionNode(
                    id=question_node_id,
                    composition_id=comp.id,
                    parent_id=node.id,
                    slot=BODY_SLOT,
                    position=position,
                    node_kind=CompositionNodeKind.BLOCK,
                    node_type=NODE_TYPE_QUESTION,
                    content=_build_question_content_snapshot(question),
                    props=previous.props if previous is not None else None,
                    schema_version=previous.schema_version if previous is not None else 1,
                    question_id=question.id,
                    question_revision=int(question.content_revision or 1),
                    created_by=actor.id,
                    updated_by=actor.id,
                )
            )
            position += 1
            answer_space = (
                plan["answer_spaces_by_source"].get(previous.id)
                if previous is not None
                else None
            )
            if answer_space is not None:
                new_children.append(
                    CompositionNode(
                        id=answer_space.id,
                        composition_id=comp.id,
                        parent_id=node.id,
                        slot=BODY_SLOT,
                        position=position,
                        node_kind=CompositionNodeKind.BLOCK,
                        node_type=NODE_TYPE_ANSWER_SPACE,
                        content=None,
                        props=answer_space.props,
                        schema_version=answer_space.schema_version,
                        source_question_node_id=question_node_id,
                        created_by=actor.id,
                        updated_by=actor.id,
                    )
                )
                position += 1

        for child in trailing_customs:
            _emit_custom(child, None)

        event_groups.append({
            "node_id": node.id,
            "question_group_id": node.question_group_id,
            "old_revision": plan["old_group_revision"],
            "new_revision": node.question_group_revision,
            "added_question_ids": plan["added"],
            "removed_question_ids": plan["removed"],
            "reordered": plan["reordered"],
        })

    db.add_all(new_children)
    await db.flush()
    await _add_event(
        db,
        composition_id=comp.id,
        composition_revision=new_revision,
        event_type="question_group_nodes_synced",
        summary=f"Synced {len(plans)} question group node(s)",
        actor_id=actor.id,
        payload={
            "old_revision": expected_revision,
            "new_revision": new_revision,
            "groups": event_groups,
        },
    )
    await db.commit()
    refreshed = await crud_composition.composition.list_nodes(db, composition_id=comp.id)
    return new_revision, refreshed


# --------------------------------------------------------------------------- #
# 定稿 (Composition Version) —— 不可变 snapshot v3
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
        if node.props:
            snap["props"] = node.props
    elif nt == NODE_TYPE_QUESTION_GROUP:
        snap["question_group_id"] = node.question_group_id
        snap["question_group_revision"] = node.question_group_revision
        snap["stimulus_id"] = node.stimulus_id
        snap["stimulus_revision"] = node.stimulus_revision
        snap["content"] = node.content
    elif nt == NODE_TYPE_QUESTION_DETAILS:
        snap["props"] = node.props
    elif nt == NODE_TYPE_ANSWER_ITEM:
        snap["source_question_node_id"] = node.source_question_node_id
        snap["props"] = node.props
    elif nt == NODE_TYPE_ANSWER_SPACE:
        snap["props"] = node.props
        if node.source_question_node_id is not None:
            snap["source_question_node_id"] = node.source_question_node_id
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
    """组装 snapshot v3:顶层元数据 + 前序展平的规范化节点。

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
        # 冻结定稿时刻的显示默认值,供导出/预览解析题目级 show 覆盖的继承基准。
        "numbering_enabled": bool(comp.numbering_enabled),
        "scoring_enabled": bool(comp.scoring_enabled),
        "question_display": {
            k: bool((comp.question_display or {}).get(k, False)) for k in ANSWER_FIELD_KEYS
        },
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
