"""题目查重:签名维护(flush 钩子)、候选查询与存量回填。设计见 docs/specs/question-dedup.md。

签名由 SQLAlchemy flush 钩子统一维护,因此所有写入路径(单题、导入、worker、MCP)都自动覆盖,
无需各自调用:
- before_flush:题目内容/选项/题型/学科/材料变化(或签名版本过期)时重算指纹与归一化文本;
  材料内容变化时重算其全部小题。
- after_flush:新题此时才有 id,在这里重写 MinHash 分桶。
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from sqlalchemy import and_, delete, event, insert, inspect, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.question import Question, QuestionDedupBand
from app.models.stimulus import Stimulus
from app.models.user import User
from app.services.question_dedup_core import (
    DEDUP_VERSION,
    SIMILAR_THRESHOLD,
    DedupKey,
    band_hashes,
    build_key,
    diff_snippets,
    MIN_FUZZY_LENGTH,
    display_text,
    match_score,
    numeric_signature,
    split_stimulus,
)

logger = logging.getLogger(__name__)

_TRACKED = ("content", "options", "q_type", "subject_id", "stimulus_id")
_PENDING = "qb_dedup_pending"
MAX_CANDIDATES = 50
MAX_RESULTS = 5
_PREVIEW_LEN = 120


# --------------------------------------------------------------------------- #
# 签名维护
# --------------------------------------------------------------------------- #
def _changed(obj: Any, attrs: Iterable[str]) -> bool:
    state = inspect(obj)
    return any(state.attrs[a].history.has_changes() for a in attrs)


def _key_for(session: Session, q: Question) -> DedupKey:
    stimulus_content = None
    if q.stimulus_id is not None:
        stimulus = session.get(Stimulus, q.stimulus_id)
        stimulus_content = stimulus.content if stimulus is not None else None
    return build_key(q_type=q.q_type, content=q.content, options=q.options, stimulus_content=stimulus_content)


@event.listens_for(Session, "before_flush")
def _before_flush(session: Session, _flush_context: Any, _instances: Any) -> None:
    candidates = [o for o in list(session.new) + list(session.dirty) if isinstance(o, Question)]
    changed_stimuli = [
        s.id for s in session.dirty
        if isinstance(s, Stimulus) and s.id is not None and _changed(s, ("content",))
    ]
    if not candidates and not changed_stimuli:
        return
    with session.no_autoflush:
        targets: Dict[int, Question] = {}
        for q in candidates:
            if q in session.new or q.dedup_version != DEDUP_VERSION or _changed(q, _TRACKED):
                targets[id(q)] = q
        if changed_stimuli:
            rows = session.execute(
                select(Question).where(Question.stimulus_id.in_(changed_stimuli))
            ).scalars().all()
            for q in rows:
                targets.setdefault(id(q), q)
        pending = session.info.setdefault(_PENDING, {})
        for q in targets.values():
            if q.content is None:
                continue
            key = _key_for(session, q)
            q.dedup_fingerprint = key.fingerprint
            q.dedup_text = key.text
            q.dedup_version = DEDUP_VERSION
            pending[id(q)] = (q, band_hashes(key))


@event.listens_for(Session, "after_flush")
def _after_flush(session: Session, _flush_context: Any) -> None:
    pending = session.info.pop(_PENDING, None)
    if not pending:
        return
    items = [(q, hashes) for q, hashes in pending.values() if q.id is not None]
    if not items:
        return
    table = QuestionDedupBand.__table__
    conn = session.connection()
    conn.execute(delete(table).where(table.c.question_id.in_([q.id for q, _ in items])))
    rows = [
        {"question_id": q.id, "band": band, "subject_id": q.subject_id, "hash": value}
        for q, hashes in items
        for band, value in enumerate(hashes)
    ]
    if rows:
        conn.execute(insert(table), rows)


@event.listens_for(Session, "after_rollback")
def _after_rollback(session: Session) -> None:
    session.info.pop(_PENDING, None)


# --------------------------------------------------------------------------- #
# 候选查询
# --------------------------------------------------------------------------- #
@dataclass
class DuplicateCandidate:
    question_id: int
    level: str  # "duplicate" | "similar"
    similarity: float
    variant: bool  # 数字或公式不同,可能是变式题
    preview: str
    q_type: str
    status: str
    created_by: Optional[str]
    created_at: Optional[datetime]
    diff: List[dict] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["similarity"] = round(self.similarity, 3)
        data["created_at"] = self.created_at.isoformat() if self.created_at else None
        return data


def key_from_payload(
    *, q_type: Any, content: Any, options: Any = None, stimulus_content: Any = None
) -> DedupKey:
    if options and not isinstance(options, (str, dict)):
        options = [o.model_dump() if hasattr(o, "model_dump") else o for o in options]
    return build_key(q_type=q_type, content=content, options=options, stimulus_content=stimulus_content)


async def stimulus_content(
    db: AsyncSession, stimulus_id: Optional[int], *, subject_id: Optional[int] = None
) -> Any:
    """材料文本;给定 subject_id 时只认同学科的材料。"""
    if stimulus_id is None:
        return None
    stimulus = await db.get(Stimulus, stimulus_id)
    if stimulus is None or (subject_id is not None and stimulus.subject_id != subject_id):
        return None
    return stimulus.content


def _base_filter(viewer: Any, subject_id: Optional[int], q_type: str, exclude_ids: Sequence[int]):
    from app.crud.crud_question import visible_questions_filter

    conds = [
        Question.subject_id == subject_id,
        Question.deleted_at.is_(None),
        Question.q_type == q_type,
        visible_questions_filter(viewer),
    ]
    if exclude_ids:
        conds.append(Question.id.notin_(list(exclude_ids)))
    return and_(*conds)


def _preview(content: Any, fallback: str) -> str:
    """展示用原文(题干纯文本),而不是归一化后的文本。"""
    from app.services.question_content import parse_json_field
    from app.services.question_content_converter import rich_doc_to_plain_text

    try:
        shown = " ".join(rich_doc_to_plain_text(parse_json_field(content)).split())
    except Exception:  # noqa: BLE001 - 预览失败不影响查重结果
        shown = ""
    shown = shown or display_text(fallback)
    return shown if len(shown) <= _PREVIEW_LEN else shown[:_PREVIEW_LEN] + "…"


async def find_duplicates(
    db: AsyncSession,
    *,
    viewer: Any,
    subject_id: Optional[int],
    key: DedupKey,
    exclude_ids: Sequence[int] = (),
    limit: int = MAX_RESULTS,
) -> List[DuplicateCandidate]:
    """同学科、调用者可见、未删除、同题型的重复/高度相似题。"""
    if subject_id is None or not key.text:
        return []
    base = _base_filter(viewer, subject_id, key.q_type, exclude_ids)
    ids = set(
        (await db.execute(
            select(Question.id).where(base, Question.dedup_fingerprint == key.fingerprint).limit(MAX_CANDIDATES)
        )).scalars().all()
    )
    hashes = band_hashes(key)
    if hashes:
        band_match = or_(*(
            and_(QuestionDedupBand.band == band, QuestionDedupBand.hash == value)
            for band, value in enumerate(hashes)
        ))
        ids |= set(
            (await db.execute(
                select(QuestionDedupBand.question_id)
                .join(Question, Question.id == QuestionDedupBand.question_id)
                .where(QuestionDedupBand.subject_id == subject_id, band_match, base)
                .distinct()
                .limit(MAX_CANDIDATES)
            )).scalars().all()
        )
    if not ids:
        return []

    rows = (await db.execute(
        select(
            Question.id, Question.dedup_fingerprint, Question.dedup_text, Question.q_type,
            Question.status, Question.created_at, Question.content, User.full_name, User.username,
        )
        .outerjoin(User, User.id == Question.created_by)
        .where(Question.id.in_(ids))
    )).all()

    signature = key.numeric_signature
    out: List[DuplicateCandidate] = []
    for row in rows:
        text = row.dedup_text or ""
        if row.dedup_fingerprint == key.fingerprint:
            level, score = "duplicate", 1.0
        else:
            if not key.fuzzy or len(text) < len(key.text) * 0.5:
                continue
            if len(split_stimulus(text)[1]) < MIN_FUZZY_LENGTH:
                continue
            score = match_score(key.text, text)
            if score < SIMILAR_THRESHOLD:
                continue
            level = "similar"
        variant = level == "similar" and numeric_signature(text) != signature
        out.append(DuplicateCandidate(
            question_id=row.id,
            level=level,
            similarity=score,
            variant=variant,
            preview=_preview(row.content, text),
            q_type=getattr(row.q_type, "value", row.q_type),
            status=row.status,
            created_by=row.full_name or row.username,
            created_at=row.created_at,
            diff=diff_snippets(text, key.text) if level == "similar" else [],
        ))
    out.sort(key=lambda c: (c.level != "duplicate", c.variant, -c.similarity, c.question_id))
    return out[:limit]


@dataclass
class BatchItem:
    ref: str
    key: DedupKey
    exclude_ids: Sequence[int] = ()


async def find_duplicates_batch(
    db: AsyncSession, *, viewer: Any, subject_id: Optional[int], items: Sequence[BatchItem]
) -> tuple[Dict[str, List[DuplicateCandidate]], Dict[str, List[Dict[str, Any]]]]:
    """返回 (与题库的候选, 批内互相重复)。批内只看「重复」与「高度相似」,按先后指向更早的条目。"""
    existing: Dict[str, List[DuplicateCandidate]] = {}
    for item in items:
        found = await find_duplicates(
            db, viewer=viewer, subject_id=subject_id, key=item.key, exclude_ids=item.exclude_ids
        )
        if found:
            existing[item.ref] = found

    intra: Dict[str, List[Dict[str, Any]]] = {}
    for i, item in enumerate(items):
        for earlier in items[:i]:
            if earlier.key.q_type != item.key.q_type or not item.key.text:
                continue
            if earlier.key.fingerprint == item.key.fingerprint:
                intra.setdefault(item.ref, []).append({"ref": earlier.ref, "level": "duplicate", "similarity": 1.0})
            elif item.key.fuzzy and earlier.key.fuzzy:
                score = match_score(earlier.key.text, item.key.text)
                if score >= SIMILAR_THRESHOLD:
                    intra.setdefault(item.ref, []).append(
                        {"ref": earlier.ref, "level": "similar", "similarity": round(score, 3)}
                    )
    return existing, intra


def blocking(candidates: Sequence[DuplicateCandidate]) -> bool:
    """需要用户确认的候选:重复与高度相似都算(见 spec 已确认决策)。"""
    return bool(candidates)


# --------------------------------------------------------------------------- #
# 存量回填
# --------------------------------------------------------------------------- #
async def backfill(db: AsyncSession, *, batch_size: int = 200) -> int:
    """为签名缺失或版本过期的题目补算。幂等;靠 flush 钩子完成计算。"""
    total = 0
    last_id = 0
    while True:
        rows = (await db.execute(
            select(Question)
            .where(
                Question.id > last_id,
                or_(Question.dedup_version.is_(None), Question.dedup_version != DEDUP_VERSION),
            )
            .order_by(Question.id)
            .limit(batch_size)
        )).scalars().all()
        if not rows:
            break
        for q in rows:
            # 版本号置空 → 视为过期,flush 钩子会重算
            q.dedup_version = None
        await db.commit()
        total += len(rows)
        last_id = rows[-1].id
    return total


def candidates_payload(candidates: Sequence[DuplicateCandidate]) -> List[Dict[str, Any]]:
    return [c.to_dict() for c in candidates]


def mapping_payload(found: Mapping[str, Sequence[DuplicateCandidate]]) -> Dict[str, List[Dict[str, Any]]]:
    return {ref: candidates_payload(cands) for ref, cands in found.items()}
