"""整卷导入:一次确认同时产出题库题目与可复用稿件。

与 `question.batch_create` 的区别在事务边界:那条路径在建题前就 commit 了 ImportTask,
无法把"建题 + 建稿"收进同一个工作单元。本模块全程只 flush,由调用方在末尾提交一次,
因此正常路径要么两类结果都在,要么都不在 —— 规格里的"稿件创建失败"只作异常恢复边界。

翻译分工:解析器只给"识别事实"(PaperExtraction),AST 由 composition_authoring.build_nodes
构造。此处只负责把 outline 里的 temp_id 换成真实 question_id,不自己拼节点。
"""
from __future__ import annotations

import hashlib
import json
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
from app.models.question_group import (
    QuestionGroup,
    QuestionGroupItem,
    QuestionRelation,
    QuestionRelationType,
    Stimulus,
)
from app.services import composition_service
from app.services.composition_authoring import AuthoringError, build_nodes
from app.services.importing.contracts import (
    OUTLINE_ANSWER_SPACE,
    OUTLINE_DEGRADED,
    OUTLINE_DETAILS_MODULE,
    OUTLINE_HEADING,
    OUTLINE_PAGE_BREAK,
    OUTLINE_QUESTION_GROUP_REF,
    OUTLINE_QUESTION_REF,
    OUTLINE_RICH_TEXT,
)
from app.services.question_content import to_db_json
from app.services.question_content_converter import markdown_to_rich_doc
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
    stimulus_temp_id_map: Dict[str, int] = field(default_factory=dict)
    question_group_temp_id_map: Dict[str, int] = field(default_factory=dict)
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
    payload.pop("id", None)
    payload.pop("children", None)
    # 旧 parent_id/parent_temp_id 只生成 QuestionRelation，不再写 questions.parent_id。
    payload.pop("parent_id", None)
    payload.setdefault("status", default_status)
    payload["subject_id"] = subject_id
    if not payload.get("source"):
        payload["source"] = source
    return schemas.QuestionCreate(**payload)


def _flatten_questions(
    questions: Sequence[Mapping[str, Any]],
) -> List[Mapping[str, Any]]:
    flattened: List[Mapping[str, Any]] = []

    def append(raw: Mapping[str, Any], parent_temp_id: Optional[str] = None) -> None:
        item = dict(raw)
        children = item.pop("children", None) or []
        temp_id = item.get("temp_id") or item.get("id")
        if temp_id:
            item["temp_id"] = str(temp_id)
        if parent_temp_id and not item.get("parent_temp_id") and not item.get("parent_id"):
            item["parent_temp_id"] = parent_temp_id
        flattened.append(item)
        for child in children:
            if isinstance(child, Mapping):
                append(child, str(temp_id) if temp_id else None)

    for raw in questions:
        append(raw)
    return flattened


def _relation_ref(raw: Mapping[str, Any]) -> Optional[str]:
    value = raw.get("parent_temp_id") or raw.get("parent_id")
    return str(value) if value is not None else None


def _enum_value(value: Any, default: str) -> str:
    value = value or default
    return value.value if hasattr(value, "value") else str(value)


def _validate_temp_references(
    *,
    questions: Sequence[Mapping[str, Any]],
    stimuli: Sequence[Mapping[str, Any]],
    question_groups: Sequence[Mapping[str, Any]],
) -> None:
    question_ids = [str(q["temp_id"]) for q in questions if q.get("temp_id")]
    if len(question_ids) != len(set(question_ids)):
        raise PaperImportError("题目 temp_id 重复，无法确定引用目标。")
    stimulus_ids = [str(s.get("temp_id") or "") for s in stimuli]
    if any(not value for value in stimulus_ids):
        raise PaperImportError("材料缺少 temp_id。")
    if len(stimulus_ids) != len(set(stimulus_ids)):
        raise PaperImportError("材料 temp_id 重复，无法确定引用目标。")
    group_ids = [str(g.get("temp_id") or "") for g in question_groups]
    if any(not value for value in group_ids):
        raise PaperImportError("题组缺少 temp_id。")
    if len(group_ids) != len(set(group_ids)):
        raise PaperImportError("题组 temp_id 重复，无法确定引用目标。")

    question_id_set = set(question_ids)
    stimulus_id_set = set(stimulus_ids)
    questions_by_id = {
        str(question["temp_id"]): question
        for question in questions
        if question.get("temp_id")
    }
    stimuli_by_id = {str(item["temp_id"]): item for item in stimuli}
    relation_edges: Dict[str, str] = {}
    for raw in questions:
        parent_ref = _relation_ref(raw)
        if parent_ref is None:
            continue
        child_ref = str(raw.get("temp_id") or "")
        if not child_ref or parent_ref not in question_id_set:
            raise PaperImportError(
                f"派生关系引用不存在的题目 temp_id：{parent_ref!r}。"
            )
        if child_ref == parent_ref:
            raise PaperImportError("派生关系不能引用题目自身。")
        relation_edges[child_ref] = parent_ref
    for child_ref in relation_edges:
        seen = {child_ref}
        cursor = relation_edges.get(child_ref)
        while cursor is not None:
            if cursor in seen:
                raise PaperImportError("派生关系形成循环。")
            seen.add(cursor)
            cursor = relation_edges.get(cursor)

    for group in question_groups:
        group_ref = str(group.get("temp_id") or "")
        stimulus_ref = str(group.get("stimulus_temp_id") or "")
        if stimulus_ref not in stimulus_id_set:
            raise PaperImportError(
                f"题组 {group_ref!r} 引用了不存在的材料 temp_id：{stimulus_ref!r}。"
            )
        member_refs = [str(value) for value in group.get("question_temp_ids") or []]
        if not member_refs:
            raise PaperImportError(f"题组 {group_ref!r} 至少需要一道题。")
        if len(member_refs) != len(set(member_refs)):
            raise PaperImportError(f"题组 {group_ref!r} 包含重复的题目引用。")
        missing = [value for value in member_refs if value not in question_id_set]
        if missing:
            raise PaperImportError(
                f"题组 {group_ref!r} 引用了不存在的题目 temp_id：{missing[0]!r}。"
            )
        visibility = _enum_value(
            group.get("visibility"), QuestionVisibility.PUBLIC.value
        )
        if visibility == QuestionVisibility.PUBLIC.value and (
            _enum_value(
                stimuli_by_id[stimulus_ref].get("visibility"),
                QuestionVisibility.PUBLIC.value,
            )
            == QuestionVisibility.PRIVATE.value
            or any(
                _visibility_of(questions_by_id[member_ref])
                == QuestionVisibility.PRIVATE.value
                for member_ref in member_refs
            )
        ):
            raise PaperImportError(
                f"公开题组 {group_ref!r} 不能引用私有材料或题目。"
            )


def _validate_outline_refs(
    questions: Sequence[Mapping[str, Any]],
    outline: Sequence[Mapping[str, Any]],
    question_groups: Sequence[Mapping[str, Any]],
) -> None:
    question_ids = {str(question.get("temp_id")) for question in questions}
    group_ids = {str(group.get("temp_id")) for group in question_groups}
    for item in outline:
        ref = str(item.get("temp_id") or "")
        if item.get("kind") == OUTLINE_QUESTION_REF and ref not in question_ids:
            raise PaperImportError(
                f"稿件结构引用了不存在的题目 temp_id：{ref!r}。"
            )
        if item.get("kind") == OUTLINE_QUESTION_GROUP_REF and ref not in group_ids:
            raise PaperImportError(
                f"稿件结构引用了不存在的题组 temp_id：{ref!r}。"
            )


def _validate_subject_ids(
    questions: Sequence[Mapping[str, Any]], subject_id: int
) -> None:
    for raw in questions:
        raw_subject_id = raw.get("subject_id")
        if raw_subject_id is not None and raw_subject_id != subject_id:
            raise PaperImportError(
                f"题目 {raw.get('temp_id')!r} 的 subject_id 与导入学科不一致。"
            )


async def preview_paper_import(
    *,
    subject_id: int,
    questions: Sequence[Mapping[str, Any]],
    outline: Sequence[Mapping[str, Any]],
    stimuli: Sequence[Mapping[str, Any]],
    question_groups: Sequence[Mapping[str, Any]],
    scope_type: ScopeType,
) -> PaperImportPreview:
    """纯内存预检:校验题目可建、私有题与共享空间的冲突、结构降级项。"""
    preview = PaperImportPreview(degraded=_collect_degraded(outline))
    questions = _flatten_questions(questions)
    importable_questions: List[Mapping[str, Any]] = []

    try:
        _validate_subject_ids(questions, subject_id)
        _validate_outline_refs(questions, outline, question_groups)
    except PaperImportError as exc:
        preview.blocking_reason = str(exc)

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
        importable_questions.append(raw)

    if scope_type is ScopeType.SHARED and _has_private_question(questions):
        preview.blocking_reason = (
            "本次导入包含私有题，私有题不能加入共享稿件；请改存到个人空间，或先调整题目可见性。"
        )
    if preview.importable_count == 0:
        preview.blocking_reason = preview.blocking_reason or "没有任何题目可以导入。"
    try:
        _validate_temp_references(
            questions=importable_questions,
            stimuli=stimuli,
            question_groups=question_groups,
        )
        for raw in stimuli:
            content = raw.get("content")
            if content is None:
                content = markdown_to_rich_doc(str(raw.get("markdown") or ""))
            schemas.StimulusCreate(
                content=content,
                status=raw.get("status") or QuestionStatus.DRAFT,
                visibility=raw.get("visibility") or QuestionVisibility.PUBLIC,
            )
    except (PaperImportError, ValidationError, ValueError) as exc:
        preview.blocking_reason = preview.blocking_reason or str(exc)

    return preview


def _resolve_outline_nodes(
    outline: Sequence[Mapping[str, Any]],
    temp_id_map: Mapping[str, int],
    group_specs: Mapping[str, Mapping[str, Any]],
    *,
    renumber: bool,
) -> List[Dict[str, Any]]:
    """outline → build_nodes 可消费的意图节点。跳过引用不存在题目的占位。"""
    specs: List[Dict[str, Any]] = []
    sequence = 0
    rendered_stimuli: set[str] = set()

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
        elif kind == OUTLINE_QUESTION_GROUP_REF:
            group = group_specs.get(str(item.get("temp_id")))
            if group is None:
                continue
            stimulus_ref = group["stimulus_ref"]
            if stimulus_ref not in rendered_stimuli:
                specs.append({"type": "rich_text", "content": group["content"]})
                rendered_stimuli.add(stimulus_ref)
            for question_id in group["question_ids"]:
                sequence += 1
                spec = {"type": "question", "question_id": question_id}
                if renumber:
                    spec["number"] = str(sequence)
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


def _fallback_outline(
    questions: Sequence[Mapping[str, Any]],
    question_groups: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """抽取未识别整卷结构时,按题目顺序退化为一串 question_ref。"""
    grouped_refs: set[str] = set()
    groups_by_first_question: Dict[str, List[Mapping[str, Any]]] = {}
    for group in question_groups:
        member_refs = [str(ref) for ref in group.get("question_temp_ids") or []]
        grouped_refs.update(member_refs)
        if member_refs:
            groups_by_first_question.setdefault(member_refs[0], []).append(group)

    outline: List[Dict[str, Any]] = []
    for question in questions:
        question_ref = str(question.get("temp_id") or "")
        for group in groups_by_first_question.get(question_ref, []):
            outline.append(
                {"kind": OUTLINE_QUESTION_GROUP_REF, "temp_id": group.get("temp_id")}
            )
        if question_ref and question_ref not in grouped_refs:
            outline.append(
                {
                    "kind": OUTLINE_QUESTION_REF,
                    "temp_id": question_ref,
                    "number": question.get("source_number"),
                }
            )
    return outline


async def _find_by_idempotency_key(
    db: AsyncSession, key: Optional[str]
) -> Optional[ImportTask]:
    if not key:
        return None
    result = await db.execute(select(ImportTask).where(ImportTask.idempotency_key == key))
    return result.scalars().first()


async def replay_paper_import(
    db: AsyncSession, idempotency_key: str
) -> Optional[PaperImportResult]:
    task = await _find_by_idempotency_key(db, idempotency_key)
    return await _result_from_task(db, task) if task is not None else None


async def _result_from_task(db: AsyncSession, task: ImportTask) -> PaperImportResult:
    summary = json.loads(task.result_summary or "{}")
    question_ids = [int(value) for value in summary.get("created_question_ids", [])]
    questions_by_id: Dict[int, Question] = {}
    if question_ids:
        rows = await db.execute(select(Question).where(Question.id.in_(question_ids)))
        questions_by_id = {question.id: question for question in rows.scalars().all()}
    result = PaperImportResult(
        import_task_id=task.id,
        created_questions=[questions_by_id[value] for value in question_ids if value in questions_by_id],
        skipped=[SkippedQuestion(**item) for item in summary.get("skipped", [])],
        degraded=[DegradedItem(**item) for item in summary.get("degraded", [])],
        composition_id=summary.get("composition_id"),
        composition_title=summary.get("composition_title"),
        temp_id_map={key: int(value) for key, value in summary.get("temp_id_map", {}).items()},
        stimulus_temp_id_map={
            key: int(value)
            for key, value in summary.get("stimulus_temp_id_map", {}).items()
        },
        question_group_temp_id_map={
            key: int(value)
            for key, value in summary.get("question_group_temp_id_map", {}).items()
        },
        reused_existing=True,
    )
    if result.composition_id is None and task.composition_state is CompositionImportState.CREATED:
        comp = await _composition_of_task(db, task.id)
        if comp is not None:
            result.composition_id = comp.id
            result.composition_title = comp.title
    return result


def _store_result_summary(task: ImportTask, result: PaperImportResult) -> None:
    task.result_summary = json.dumps(
        {
            "created_question_ids": [question.id for question in result.created_questions],
            "skipped": [vars(item) for item in result.skipped],
            "degraded": [vars(item) for item in result.degraded],
            "composition_id": result.composition_id,
            "composition_title": result.composition_title,
            "temp_id_map": result.temp_id_map,
            "stimulus_temp_id_map": result.stimulus_temp_id_map,
            "question_group_temp_id_map": result.question_group_temp_id_map,
        },
        ensure_ascii=False,
    )


async def commit_paper_import(
    db: AsyncSession,
    *,
    actor,
    subject_id: int,
    scope_type: ScopeType,
    owner_id: Optional[int],
    questions: Sequence[Mapping[str, Any]],
    outline: Sequence[Mapping[str, Any]],
    stimuli: Sequence[Mapping[str, Any]],
    question_groups: Sequence[Mapping[str, Any]],
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
    import_task: Optional[ImportTask] = None,
) -> PaperImportResult:
    """在单一工作单元内完成建任务、建题、建稿、写 AST。调用方负责 commit。"""
    questions = _flatten_questions(questions)
    if not questions:
        raise PaperImportError("没有选中任何题目。")

    _validate_subject_ids(questions, subject_id)
    _validate_temp_references(
        questions=questions,
        stimuli=stimuli,
        question_groups=question_groups,
    )
    _validate_outline_refs(questions, outline, question_groups)

    existing = await _find_by_idempotency_key(db, idempotency_key)
    if existing is not None:
        return await _result_from_task(db, existing)

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
    _validate_temp_references(
        questions=[raw for raw, _question_in in plans],
        stimuli=stimuli,
        question_groups=question_groups,
    )

    stimulus_plans: List[tuple[Mapping[str, Any], schemas.StimulusCreate]] = []
    for raw in stimuli:
        content = raw.get("content")
        if content is None:
            content = markdown_to_rich_doc(str(raw.get("markdown") or ""))
        try:
            stimulus_in = schemas.StimulusCreate(
                content=content,
                status=raw.get("status") or default_status,
                visibility=raw.get("visibility") or QuestionVisibility.PUBLIC,
            )
        except (ValidationError, ValueError) as exc:
            raise PaperImportError(
                f"材料 {raw.get('temp_id')!r} 内容无效：{exc}"
            ) from exc
        stimulus_plans.append((raw, stimulus_in))

    # 阶段 2：写库。以下操作全部只 flush，由 capability 在末尾统一 commit。
    if import_task is None:
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
    else:
        import_task.status = ImportTaskStatus.COMPLETED
        import_task.error_message = None
        import_task.composition_state = CompositionImportState.NOT_REQUESTED
    await db.flush()

    created: List[Question] = []
    temp_id_map: Dict[str, int] = {}

    for raw, question_in in plans:
        question = await question_service.create_question(
            db=db,
            question_in=question_in,
            user_id=actor.id,
            import_task_id=import_task.id,
            commit=False,
        )
        created.append(question)
        if raw.get("temp_id"):
            temp_id_map[str(raw["temp_id"])] = question.id

    for raw, _question_in in plans:
        parent_ref = _relation_ref(raw)
        if parent_ref is None:
            continue
        db.add(
            QuestionRelation(
                source_question_id=temp_id_map[parent_ref],
                target_question_id=temp_id_map[str(raw["temp_id"])],
                relation_type=QuestionRelationType.DECOMPOSED_FROM.value,
                created_by=actor.id,
            )
        )
    await db.flush()

    stimulus_temp_id_map: Dict[str, int] = {}
    stimulus_content_map: Dict[str, dict] = {}
    for raw, stimulus_in in stimulus_plans:
        stimulus = Stimulus(
            subject_id=subject_id,
            content=to_db_json(stimulus_in.content),
            status=stimulus_in.status.value,
            visibility=stimulus_in.visibility.value,
            source=raw.get("source") or filename,
            metadata_json=json.dumps(raw.get("metadata") or {}, ensure_ascii=False),
            created_by=actor.id,
            updated_by=actor.id,
        )
        db.add(stimulus)
        await db.flush()
        stimulus_ref = str(raw["temp_id"])
        stimulus_temp_id_map[stimulus_ref] = stimulus.id
        stimulus_content_map[stimulus_ref] = stimulus_in.content

    question_group_temp_id_map: Dict[str, int] = {}
    group_specs: Dict[str, Dict[str, Any]] = {}
    for raw in question_groups:
        group_ref = str(raw["temp_id"])
        stimulus_ref = str(raw["stimulus_temp_id"])
        visibility = _enum_value(raw.get("visibility"), QuestionVisibility.PUBLIC.value)
        group = QuestionGroup(
            subject_id=subject_id,
            stimulus_id=stimulus_temp_id_map[stimulus_ref],
            status=_enum_value(raw.get("status"), default_status.value),
            visibility=visibility,
            source=raw.get("source") or filename,
            metadata_json=json.dumps(raw.get("metadata") or {}, ensure_ascii=False),
            created_by=actor.id,
            updated_by=actor.id,
        )
        db.add(group)
        await db.flush()
        question_ids = [temp_id_map[str(ref)] for ref in raw["question_temp_ids"]]
        db.add_all(
            QuestionGroupItem(group_id=group.id, question_id=question_id, position=position)
            for position, question_id in enumerate(question_ids)
        )
        question_group_temp_id_map[group_ref] = group.id
        group_specs[group_ref] = {
            "content": stimulus_content_map[stimulus_ref],
            "question_ids": question_ids,
            "stimulus_ref": stimulus_ref,
        }
    await db.flush()

    result = PaperImportResult(
        import_task_id=import_task.id,
        created_questions=created,
        skipped=skipped,
        degraded=_collect_degraded(outline),
        temp_id_map=temp_id_map,
        stimulus_temp_id_map=stimulus_temp_id_map,
        question_group_temp_id_map=question_group_temp_id_map,
    )

    if not save_as_composition:
        _store_result_summary(import_task, result)
        return result

    effective_outline = list(outline) or _fallback_outline(questions, question_groups)
    specs = _resolve_outline_nodes(
        effective_outline,
        temp_id_map,
        group_specs,
        renumber=renumber,
    )
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
        commit=False,
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
        commit=False,
    )

    import_task.composition_state = CompositionImportState.CREATED
    result.composition_id = comp.id
    result.composition_title = comp.title
    _store_result_summary(import_task, result)
    return result


async def commit_extracted_paper_import(
    db: AsyncSession,
    *,
    actor,
    subject_id: int,
    extraction: Mapping[str, Any],
    import_task: ImportTask,
) -> PaperImportResult:
    """将解析器产物归一化后交给整卷写服务，供无 HTTP 的 worker 使用。"""
    from app.services.importing.review import (
        extracted_stimuli_to_review,
        extracted_to_v2_review,
    )

    paper = extraction.get("paper") or {}
    questions = extracted_to_v2_review(
        extraction.get("questions") or [], subject_id=subject_id
    )
    return await commit_paper_import(
        db,
        actor=actor,
        subject_id=subject_id,
        scope_type=ScopeType.PERSONAL,
        owner_id=actor.id,
        questions=questions,
        outline=paper.get("outline") or [],
        stimuli=extracted_stimuli_to_review(extraction.get("stimuli") or []),
        question_groups=extraction.get("question_groups") or [],
        save_as_composition=bool(paper),
        title=paper.get("suggested_title") or import_task.original_filename,
        proceed_with_partial=True,
        default_status=QuestionStatus.PENDING,
        filename=import_task.original_filename,
        file_path=import_task.file_path,
        import_task=import_task,
    )


async def _composition_of_task(db: AsyncSession, task_id: int):
    from app.models.composition import Composition

    result = await db.execute(
        select(Composition).where(Composition.source_import_task_id == task_id)
    )
    return result.scalars().first()
