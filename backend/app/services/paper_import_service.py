"""整卷导入:一次确认同时产出题库题目与可复用稿件。

与 `question.batch_create` 的区别在事务边界:那条路径在建题前就 commit 了 ImportTask,
无法把"建题 + 建稿"收进同一个工作单元。本模块全程只 flush,由调用方在末尾提交一次,
因此正常路径要么两类结果都在,要么都不在 —— 规格里的"稿件创建失败"只作异常恢复边界。

翻译分工:解析器只给"识别事实"(PaperExtraction),AST 由 composition_authoring.build_nodes
构造。此处只负责把 outline 里的 temp_id 换成真实 question_id,不自己拼节点。
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Sequence

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.models.composition import ScopeType
from app.models.import_task import (
    CompositionImportState,
    ImportTask,
    ImportTaskStatus,
)
from app.models.question import Question, QuestionStatus, QuestionVisibility
from app.services import composition_service
from app.services.composition_authoring import AuthoringError, build_nodes
from app.services.importing.contracts import (
    OUTLINE_ANSWER_SPACE,
    OUTLINE_DEGRADED,
    OUTLINE_DETAILS_MODULE,
    OUTLINE_HEADING,
    OUTLINE_PAGE_BREAK,
    OUTLINE_QUESTION_REF,
    OUTLINE_RICH_TEXT,
)
from app.services.question_service import question_service

logger = logging.getLogger(__name__)


class PaperImportError(ValueError):
    """整卷导入的领域错误;文案直接面向用户。"""


@dataclass
class SkippedQuestion:
    index: int
    temp_id: Optional[str]
    message: str


@dataclass
class DegradedItem:
    reason: str
    excerpt: str


@dataclass
class PaperImportPreview:
    """预检结果:不写库,用于让用户在确认前看到会发生什么。"""

    importable_count: int = 0
    skipped: List[SkippedQuestion] = field(default_factory=list)
    degraded: List[DegradedItem] = field(default_factory=list)
    blocking_reason: Optional[str] = None

    @property
    def has_blocking_issue(self) -> bool:
        return self.blocking_reason is not None


@dataclass
class PaperImportResult:
    import_task_id: int
    created_questions: List[Question] = field(default_factory=list)
    skipped: List[SkippedQuestion] = field(default_factory=list)
    degraded: List[DegradedItem] = field(default_factory=list)
    composition_id: Optional[int] = None
    composition_title: Optional[str] = None
    temp_id_map: Dict[str, int] = field(default_factory=dict)
    reused_existing: bool = False


def file_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _visibility_of(raw: Mapping[str, Any]) -> str:
    value = raw.get("visibility") or QuestionVisibility.PUBLIC.value
    return value.value if hasattr(value, "value") else str(value)


def _has_private_question(questions: Sequence[Mapping[str, Any]]) -> bool:
    return any(
        _visibility_of(q) == QuestionVisibility.PRIVATE.value for q in questions
    )


def _excerpt(text: str, limit: int = 60) -> str:
    flat = " ".join((text or "").split())
    return flat if len(flat) <= limit else f"{flat[:limit]}…"


def _collect_degraded(outline: Sequence[Mapping[str, Any]]) -> List[DegradedItem]:
    return [
        DegradedItem(
            reason=str(item.get("reason") or "结构无法完整表达，已降级为文本"),
            excerpt=_excerpt(str(item.get("markdown") or "")),
        )
        for item in outline
        if item.get("kind") == OUTLINE_DEGRADED
    ]


def _build_question_create(
    raw: Mapping[str, Any],
    *,
    subject_id: Optional[int],
    default_status: QuestionStatus,
    source: Optional[str],
) -> schemas.QuestionCreate:
    payload = dict(raw)
    payload.pop("temp_id", None)
    payload.pop("parent_temp_id", None)
    payload.pop("source_number", None)
    payload.pop("warnings", None)
    payload.pop("selected", None)
    payload.pop("uid", None)
    payload.setdefault("status", default_status)
    payload["subject_id"] = payload.get("subject_id") or subject_id
    if not payload.get("source"):
        payload["source"] = source
    return schemas.QuestionCreate(**payload)


async def preview_paper_import(
    *,
    questions: Sequence[Mapping[str, Any]],
    outline: Sequence[Mapping[str, Any]],
    scope_type: ScopeType,
) -> PaperImportPreview:
    """纯内存预检:校验题目可建、私有题与共享空间的冲突、结构降级项。"""
    preview = PaperImportPreview(degraded=_collect_degraded(outline))

    for index, raw in enumerate(questions):
        try:
            _build_question_create(
                raw, subject_id=raw.get("subject_id"), default_status=QuestionStatus.DRAFT, source=None
            )
        except (ValidationError, ValueError) as exc:
            preview.skipped.append(
                SkippedQuestion(index=index, temp_id=raw.get("temp_id"), message=str(exc))
            )
            continue
        preview.importable_count += 1

    if scope_type is ScopeType.SHARED and _has_private_question(questions):
        preview.blocking_reason = (
            "本次导入包含私有题，私有题不能加入共享稿件；请改存到个人空间，或先调整题目可见性。"
        )
    if preview.importable_count == 0:
        preview.blocking_reason = preview.blocking_reason or "没有任何题目可以导入。"

    return preview


def _resolve_outline_nodes(
    outline: Sequence[Mapping[str, Any]],
    temp_id_map: Mapping[str, int],
    *,
    renumber: bool,
) -> List[Dict[str, Any]]:
    """outline → build_nodes 可消费的意图节点。跳过引用不存在题目的占位。"""
    specs: List[Dict[str, Any]] = []
    sequence = 0

    for item in outline:
        kind = item.get("kind")

        if kind == OUTLINE_QUESTION_REF:
            question_id = temp_id_map.get(str(item.get("temp_id")))
            if question_id is None:
                continue
            sequence += 1
            number = str(sequence) if renumber else item.get("number")
            spec: Dict[str, Any] = {"type": "question", "question_id": question_id}
            if number is not None:
                spec["number"] = number
            if item.get("score") is not None:
                spec["score"] = item["score"]
            specs.append(spec)
        elif kind == OUTLINE_HEADING:
            specs.append(
                {"type": "heading", "text": item.get("text") or "", "level": item.get("level") or 2}
            )
        elif kind in (OUTLINE_RICH_TEXT, OUTLINE_DEGRADED):
            markdown = item.get("markdown") or ""
            if markdown.strip():
                specs.append({"type": "rich_text", "markdown": markdown})
        elif kind == OUTLINE_PAGE_BREAK:
            specs.append({"type": "page_break"})
        elif kind == OUTLINE_ANSWER_SPACE:
            specs.append(
                {
                    "type": "answer_space",
                    "lines": item.get("lines") or 4,
                    "style": item.get("style") or "lined",
                }
            )
        elif kind == OUTLINE_DETAILS_MODULE:
            specs.append(
                {
                    "type": "question_details",
                    "details_scope": item.get("scope") or "all",
                    "details_fields": item.get("fields") or {"answer": True},
                }
            )

    return specs


def _fallback_outline(questions: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """抽取未识别整卷结构时,按题目顺序退化为一串 question_ref。"""
    return [
        {
            "kind": OUTLINE_QUESTION_REF,
            "temp_id": q.get("temp_id"),
            "number": q.get("source_number"),
        }
        for q in questions
        if q.get("temp_id")
    ]


async def _find_by_idempotency_key(
    db: AsyncSession, key: Optional[str]
) -> Optional[ImportTask]:
    if not key:
        return None
    result = await db.execute(select(ImportTask).where(ImportTask.idempotency_key == key))
    return result.scalars().first()


async def commit_paper_import(
    db: AsyncSession,
    *,
    actor,
    subject_id: int,
    scope_type: ScopeType,
    owner_id: Optional[int],
    questions: Sequence[Mapping[str, Any]],
    outline: Sequence[Mapping[str, Any]],
    save_as_composition: bool,
    title: Optional[str] = None,
    folder_id: Optional[int] = None,
    renumber: bool = False,
    proceed_with_partial: bool = False,
    default_status: QuestionStatus = QuestionStatus.PENDING,
    filename: Optional[str] = None,
    file_path: Optional[str] = None,
    content_sha256: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> PaperImportResult:
    """在单一工作单元内完成建任务、建题、建稿、写 AST。调用方负责 commit。"""
    if not questions:
        raise PaperImportError("没有选中任何题目。")

    existing = await _find_by_idempotency_key(db, idempotency_key)
    if existing is not None:
        # 同一请求重放:返回既有结果,不重复建题建稿。
        result = PaperImportResult(import_task_id=existing.id, reused_existing=True)
        if existing.composition_state is CompositionImportState.CREATED:
            comp = await _composition_of_task(db, existing.id)
            if comp is not None:
                result.composition_id = comp.id
                result.composition_title = comp.title
        return result

    if save_as_composition and scope_type is ScopeType.SHARED and _has_private_question(questions):
        raise PaperImportError(
            "本次导入包含私有题，私有题不能加入共享稿件；请改存到个人空间，或先调整题目可见性。"
        )

    # 阶段 1：纯内存构造，先把"哪些题能建"定下来。
    # 底层 CRUD 每建一题即自行 commit，无法整体回滚，因此所有可预知的拒绝都必须
    # 发生在写库之前 —— 否则用户选择"取消"时数据库里已经躺着半份题目。
    plans: List[tuple[Mapping[str, Any], schemas.QuestionCreate]] = []
    skipped: List[SkippedQuestion] = []
    for index, raw in enumerate(questions):
        try:
            question_in = _build_question_create(
                raw, subject_id=subject_id, default_status=default_status, source=filename
            )
        except (ValidationError, ValueError) as exc:
            logger.warning("paper import: skip question #%d: %s", index, exc)
            skipped.append(
                SkippedQuestion(index=index, temp_id=raw.get("temp_id"), message=str(exc))
            )
            continue
        plans.append((raw, question_in))

    if not plans:
        raise PaperImportError("选中的题目均未能入库，未创建任何内容。")
    if skipped and not proceed_with_partial:
        raise PaperImportError(
            f"有 {len(skipped)} 道题目未能入库。请确认是否仅用已成功的题目继续创建稿件。"
        )

    # 阶段 2：写库。
    import_task = ImportTask(
        user_id=actor.id,
        description=filename or f"整卷导入 {len(plans)} 道题目",
        source="paper_import",
        file_path=file_path or "virtual",
        original_filename=filename or "paper_import.json",
        file_type="json",
        status=ImportTaskStatus.COMPLETED,
        content_sha256=content_sha256,
        idempotency_key=idempotency_key,
        composition_state=CompositionImportState.NOT_REQUESTED,
    )
    db.add(import_task)
    await db.flush()

    created: List[Question] = []
    temp_id_map: Dict[str, int] = {}

    # 母题先建，子题拿到真实 parent_id 后再建。
    roots = [(raw, qc) for raw, qc in plans if not raw.get("parent_temp_id")]
    children = [(raw, qc) for raw, qc in plans if raw.get("parent_temp_id")]

    for raw, question_in in roots:
        question = await question_service.create_question(
            db=db, question_in=question_in, user_id=actor.id, import_task_id=import_task.id
        )
        created.append(question)
        if raw.get("temp_id"):
            temp_id_map[str(raw["temp_id"])] = question.id

    for raw, question_in in children:
        parent_id = temp_id_map.get(str(raw.get("parent_temp_id")))
        if parent_id is None:
            skipped.append(
                SkippedQuestion(
                    index=-1,
                    temp_id=raw.get("temp_id"),
                    message="母题未能成功入库，子题一并跳过",
                )
            )
            continue
        question_in.parent_id = parent_id
        question = await question_service.create_question(
            db=db, question_in=question_in, user_id=actor.id, import_task_id=import_task.id
        )
        created.append(question)
        if raw.get("temp_id"):
            temp_id_map[str(raw["temp_id"])] = question.id

    result = PaperImportResult(
        import_task_id=import_task.id,
        created_questions=created,
        skipped=skipped,
        degraded=_collect_degraded(outline),
        temp_id_map=temp_id_map,
    )

    if not save_as_composition:
        return result

    effective_outline = list(outline) or _fallback_outline(questions)
    specs = _resolve_outline_nodes(effective_outline, temp_id_map, renumber=renumber)
    try:
        nodes = build_nodes(specs)
    except AuthoringError as exc:
        raise PaperImportError(f"整卷结构无法转换为稿件：{exc}") from exc

    comp = await composition_service.create_composition(
        db,
        subject_id=subject_id,
        scope_type=scope_type,
        owner_id=owner_id,
        actor=actor,
        title=(title or "").strip() or (filename or "未命名试卷"),
        description=None,
        folder_id=folder_id,
        numbering_enabled=True,
    )
    comp.source_import_task_id = import_task.id
    # 来源信息在创建时固化:源文件后续被清理也不影响稿件可读性。
    comp.source_snapshot = {
        "import_task_id": import_task.id,
        "original_filename": filename,
        "imported_at": datetime.utcnow().isoformat(),
        "question_count": len(created),
    }
    await db.flush()

    await composition_service.replace_nodes(
        db,
        comp=comp,
        actor=actor,
        expected_revision=comp.revision,
        batch_id=idempotency_key,
        items=nodes,
    )

    import_task.composition_state = CompositionImportState.CREATED
    result.composition_id = comp.id
    result.composition_title = comp.title
    return result


async def _composition_of_task(db: AsyncSession, task_id: int):
    from app.models.composition import Composition

    result = await db.execute(
        select(Composition).where(Composition.source_import_task_id == task_id)
    )
    return result.scalars().first()
