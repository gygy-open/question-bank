"""组稿 (Composition) 域的领域服务 —— 第二阶段。

职责边界(与 crud_composition 划分):
- crud 负责 scoped 读取(强制 subject/scope/owner)。
- 本模块负责 **写路径的领域不变量与事务**:父目录一致性、自引用/祖先环检测、
  软删除非空拦截、组稿乐观锁(条件 UPDATE),以及与业务变更 **同事务** 写 CompositionEvent。

错误约定(与仓库 FastAPI 风格一致):
- 跨 scope/subject/owner 不可见 → 404(防枚举)。
- 版本冲突 / 删除非空目录 → 409。
- 结构非法(自引用父、祖先环)→ 400。
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import crud_composition
from app.models.composition import (
    Composition,
    CompositionBlock,
    CompositionBlockType,
    CompositionEvent,
    CompositionVersion,
    Folder,
    ScopeType,
)
from app.models.question import Question, QuestionType
from app.models.user import User
from app.schemas.composition import CompositionBlockReplaceItem, QuestionSnapshot
from app.services.question_content import parse_json_field

SNAPSHOT_SCHEMA_VERSION = 1


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
# CompositionBlock 批量替换(画布契约)
# --------------------------------------------------------------------------- #
async def _resolve_question_ref(
    db: AsyncSession,
    *,
    question_id: int,
    subject_id: int,
) -> int:
    """校验 question block 引用并返回服务端钉住的 content_revision。

    缺失 / 软删除 / 跨学科统一 422(不信任客户端传入的 revision)。
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
    return int(question.content_revision or 1)


async def replace_blocks(
    db: AsyncSession,
    *,
    comp: Composition,
    actor: User,
    expected_revision: int,
    batch_id: Optional[str],
    items: List[CompositionBlockReplaceItem],
) -> tuple[int, dict, List[CompositionBlock]]:
    """一次事务内整体替换 composition 的 block 序列。

    数组顺序即 sequence;已有 block 按 id 原地更新并保留身份,未出现的旧 block 删除,
    带 temp_id 的新 block 插入并回填 id_map。question block 的 revision 由服务端钉住。
    任何校验失败不产生部分更改;组稿乐观锁冲突 409。
    """
    existing = await crud_composition.composition.list_blocks(db, composition_id=comp.id)
    existing_by_id = {block.id: block for block in existing}

    # 1) 全量校验(不产生任何写入):已有 id 必须属于该 composition;question 引用合法。
    referenced_ids: set[int] = set()
    pinned_revisions: dict[int, int] = {}
    for idx, item in enumerate(items):
        if item.id is not None:
            if item.id not in existing_by_id:
                raise _not_found("Block")
            referenced_ids.add(item.id)
        if item.block_type == CompositionBlockType.QUESTION:
            assert item.question_id is not None  # schema 已保证
            pinned_revisions[idx] = await _resolve_question_ref(
                db,
                question_id=item.question_id,
                subject_id=comp.subject_id,
            )

    # 2) 乐观锁:先条件自增 revision;冲突则 409 且此时尚未改动任何 block。
    new_revision = await _guarded_write(
        db,
        composition_id=comp.id,
        expected_revision=expected_revision,
        values={"updated_by": actor.id, "updated_at": datetime.utcnow()},
        require_deleted=False,
    )

    # 3) 应用变更:删除缺席、原地更新、插入新增,并重排 sequence。
    removed_ids = [bid for bid in existing_by_id if bid not in referenced_ids]
    for bid in removed_ids:
        await db.delete(existing_by_id[bid])

    id_map: dict[str, int] = {}
    added = 0
    updated = 0
    for idx, item in enumerate(items):
        question_revision = pinned_revisions.get(idx)
        if item.id is not None:
            block = existing_by_id[item.id]
            block.sequence = idx
            block.block_type = item.block_type
            block.content = item.content
            block.props = item.props
            block.schema_version = item.schema_version
            block.question_id = item.question_id
            block.question_revision = question_revision
            block.updated_by = actor.id
            db.add(block)
            updated += 1
        else:
            block = CompositionBlock(
                composition_id=comp.id,
                sequence=idx,
                block_type=item.block_type,
                content=item.content,
                props=item.props,
                schema_version=item.schema_version,
                question_id=item.question_id,
                question_revision=question_revision,
                created_by=actor.id,
                updated_by=actor.id,
            )
            db.add(block)
            await db.flush()
            assert item.temp_id is not None
            id_map[item.temp_id] = block.id
            added += 1

    # 4) 与业务变更同事务写一条时间线事件。
    resolved_batch_id = batch_id or uuid.uuid4().hex
    await _add_event(
        db,
        composition_id=comp.id,
        composition_revision=new_revision,
        event_type="blocks_replaced",
        summary=f"Replaced blocks (+{added}/~{updated}/-{len(removed_ids)})",
        actor_id=actor.id,
        batch_id=resolved_batch_id,
        payload={
            "added": added,
            "updated": updated,
            "removed": len(removed_ids),
            "removed_ids": removed_ids,
        },
    )

    await db.commit()

    refreshed = await crud_composition.composition.list_blocks(db, composition_id=comp.id)
    return new_revision, id_map, refreshed


# --------------------------------------------------------------------------- #
# 定稿 (Composition Version) —— 不可变 snapshot
# --------------------------------------------------------------------------- #
def _build_question_snapshot(question: Question) -> Dict[str, Any]:
    """冻结单个题目为原生 JSON 投影(经 Pydantic 结构化,不直接序列化 ORM)。"""
    q_type = question.q_type.value if isinstance(question.q_type, QuestionType) else question.q_type
    snapshot = QuestionSnapshot(
        id=question.id,
        content_revision=int(question.content_revision or 1),
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


def _build_snapshot(
    comp: Composition,
    blocks: List[CompositionBlock],
    questions_by_id: Dict[int, Question],
    finalized_at: datetime,
) -> Dict[str, Any]:
    """组装 snapshot v1:顶层元数据 + 按 sequence 的 block 投影。

    answer_summary 的 resolved_question_ids 使用 question_id(按 ADR),按 sequence 去重保序:
    mode=all → 整稿全部 question block IDs;mode=before → 该 summary 之前的 question block IDs。
    """
    ordered = sorted(blocks, key=lambda b: b.sequence)

    # 整稿全部 question_id(按 sequence 去重保序),供 mode=all 使用。
    all_ids: List[int] = []
    all_seen: set[int] = set()
    for block in ordered:
        if block.block_type == CompositionBlockType.QUESTION and block.question_id is not None:
            if block.question_id not in all_seen:
                all_seen.add(block.question_id)
                all_ids.append(block.question_id)

    block_snaps: List[Dict[str, Any]] = []
    before_ids: List[int] = []
    before_seen: set[int] = set()
    for block in ordered:
        bt = block.block_type
        if bt == CompositionBlockType.RICH_TEXT:
            block_snaps.append({"block_type": "rich_text", "content": block.content})
        elif bt == CompositionBlockType.HEADING:
            block_snaps.append(
                {
                    "block_type": "heading",
                    "content": block.content,
                    "props": {"level": (block.props or {}).get("level")},
                }
            )
        elif bt == CompositionBlockType.PAGE_BREAK:
            block_snaps.append({"block_type": "page_break"})
        elif bt == CompositionBlockType.QUESTION:
            question = questions_by_id.get(block.question_id) if block.question_id else None
            block_snaps.append(
                {
                    "block_type": "question",
                    "question_id": block.question_id,
                    "question_revision": block.question_revision,
                    "question": _build_question_snapshot(question) if question else None,
                }
            )
            if block.question_id is not None and block.question_id not in before_seen:
                before_seen.add(block.question_id)
                before_ids.append(block.question_id)
        elif bt == CompositionBlockType.ANSWER_SUMMARY:
            mode = (block.props or {}).get("mode")
            resolved = list(all_ids) if mode == "all" else list(before_ids)
            block_snaps.append(
                {
                    "block_type": "answer_summary",
                    "props": {"mode": mode},
                    "resolved_question_ids": resolved,
                }
            )

    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "composition_id": comp.id,
        "source_revision": comp.revision,
        "title": comp.title,
        "subject_id": comp.subject_id,
        "finalized_at": finalized_at.isoformat(),
        "blocks": block_snaps,
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

    blocks = await crud_composition.composition.list_blocks(db, composition_id=comp.id)
    question_ids = {
        block.question_id
        for block in blocks
        if block.block_type == CompositionBlockType.QUESTION and block.question_id is not None
    }
    questions_by_id: Dict[int, Question] = {}
    if question_ids:
        result = await db.execute(select(Question).where(Question.id.in_(question_ids)))
        questions_by_id = {q.id: q for q in result.scalars().all()}

    finalized_at = datetime.utcnow()
    snapshot = _build_snapshot(comp, blocks, questions_by_id, finalized_at)

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
