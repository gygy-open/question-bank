"""Dashboard 统计。所有题目口径与题库列表一致:学科内、未软删除、对当前用户可见。"""
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.crud_question import visible_questions_filter
from app.models.activity_log import ActivityLog
from app.models.composition import Composition, ScopeType
from app.models.knowledge_point import KnowledgePoint
from app.models.question import (
    Question,
    QuestionStatus,
    QuestionType,
    QuestionVisibility,
    question_knowledge_points,
    question_tags,
)
from app.models.stimulus import Stimulus
from app.models.tag import Tag
from app.models.user import User
from app.schemas.dashboard import (
    Contributor,
    CountItem,
    DashboardContributors,
    DashboardDistribution,
    DashboardKnowledgeCoverage,
    DashboardOverview,
    DashboardStats,
    KnowledgePointCount,
    TrendPoint,
)

TREND_DAYS = 30
TOP_KP_LIMIT = 10
UNCOVERED_KP_LIMIT = 10
CONTRIBUTOR_LIMIT = 10


def _question_scope(subject_id: int, viewer: User) -> Any:
    return and_(
        Question.subject_id == subject_id,
        Question.deleted_at.is_(None),
        visible_questions_filter(viewer),
    )


async def _count(db: AsyncSession, stmt: Any) -> int:
    return int((await db.scalar(stmt)) or 0)


async def _group_counts(db: AsyncSession, column: Any, scope: Any) -> Dict[Any, int]:
    rows = await db.execute(
        select(column, func.count(Question.id)).where(scope).group_by(column)
    )
    return {key: int(n) for key, n in rows.all()}


def _enum_value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _ordered(counts: Dict[Any, int], keys: List[str]) -> List[CountItem]:
    normalized: Dict[str, int] = {}
    for k, n in counts.items():
        if k is None:
            continue
        key = _enum_value(k)
        normalized[key] = normalized.get(key, 0) + n
    items = [CountItem(key=k, count=normalized.pop(k, 0)) for k in keys]
    items.extend(CountItem(key=k, count=n) for k, n in sorted(normalized.items()))
    return items


async def _overview(db: AsyncSession, subject_id: int, viewer: User, scope: Any, now: datetime) -> DashboardOverview:
    q_count = select(func.count(Question.id)).where(scope)
    status_counts = await _group_counts(db, Question.status, scope)

    stimulus_scope = and_(
        Stimulus.subject_id == subject_id,
        Stimulus.deleted_at.is_(None),
    )
    if not viewer.is_superuser:
        stimulus_scope = and_(
            stimulus_scope,
            or_(
                Stimulus.visibility == QuestionVisibility.PUBLIC.value,
                Stimulus.created_by == viewer.id,
            ),
        )

    composition_scope = and_(
        Composition.subject_id == subject_id,
        Composition.deleted_at.is_(None),
        or_(
            Composition.scope_type == ScopeType.SHARED,
            and_(Composition.scope_type == ScopeType.PERSONAL, Composition.owner_id == viewer.id),
        ),
    )

    return DashboardOverview(
        total_questions=await _count(db, q_count),
        new_questions_7d=await _count(db, q_count.where(Question.created_at >= now - timedelta(days=7))),
        published=status_counts.get(QuestionStatus.PUBLISHED.value, 0),
        pending=status_counts.get(QuestionStatus.PENDING.value, 0),
        stimuli=await _count(db, select(func.count(Stimulus.id)).where(stimulus_scope)),
        compositions=await _count(db, select(func.count(Composition.id)).where(composition_scope)),
        knowledge_points=await _count(
            db, select(func.count(KnowledgePoint.id)).where(KnowledgePoint.subject_id == subject_id)
        ),
        tags=await _count(db, select(func.count(Tag.id)).where(Tag.subject_id == subject_id)),
    )


async def _distribution(db: AsyncSession, scope: Any) -> DashboardDistribution:
    return DashboardDistribution(
        q_type=_ordered(await _group_counts(db, Question.q_type, scope), [t.value for t in QuestionType]),
        status=_ordered(await _group_counts(db, Question.status, scope), [s.value for s in QuestionStatus]),
        difficulty=_ordered(
            {str(k): n for k, n in (await _group_counts(db, Question.difficulty, scope)).items() if k is not None},
            [str(i) for i in range(1, 6)],
        ),
        visibility=_ordered(
            await _group_counts(db, Question.visibility, scope), [v.value for v in QuestionVisibility]
        ),
    )


async def _knowledge_coverage(db: AsyncSession, subject_id: int, scope: Any) -> DashboardKnowledgeCoverage:
    qkp = question_knowledge_points
    visible_links = (
        select(qkp.c.knowledge_point_id, func.count(distinct(Question.id)).label("n"))
        .join(Question, Question.id == qkp.c.question_id)
        .where(scope)
        .group_by(qkp.c.knowledge_point_id)
        .subquery()
    )
    count_col = func.coalesce(visible_links.c.n, 0)
    base = (
        select(KnowledgePoint.id, KnowledgePoint.name, count_col.label("n"))
        .outerjoin(visible_links, visible_links.c.knowledge_point_id == KnowledgePoint.id)
        .where(KnowledgePoint.subject_id == subject_id)
    )

    total = await _count(db, select(func.count(KnowledgePoint.id)).where(KnowledgePoint.subject_id == subject_id))
    covered = await _count(db, select(func.count()).select_from(visible_links))
    top_rows = await db.execute(
        base.where(count_col > 0).order_by(count_col.desc(), KnowledgePoint.id).limit(TOP_KP_LIMIT)
    )
    uncovered_rows = await db.execute(
        base.where(count_col == 0).order_by(KnowledgePoint.id).limit(UNCOVERED_KP_LIMIT)
    )

    q_count = select(func.count(Question.id)).where(scope)
    without_kp = await _count(
        db, q_count.where(~select(qkp.c.question_id).where(qkp.c.question_id == Question.id).exists())
    )
    without_tag = await _count(
        db,
        q_count.where(
            ~select(question_tags.c.question_id).where(question_tags.c.question_id == Question.id).exists()
        ),
    )

    return DashboardKnowledgeCoverage(
        total=total,
        covered=covered,
        top=[KnowledgePointCount(id=i, name=name, count=int(n)) for i, name, n in top_rows.all()],
        uncovered=[KnowledgePointCount(id=i, name=name, count=0) for i, name, _ in uncovered_rows.all()],
        questions_without_kp=without_kp,
        questions_without_tag=without_tag,
    )


def _as_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


async def _trend(db: AsyncSession, scope: Any, now: datetime) -> List[TrendPoint]:
    today = now.date()
    start_day = today - timedelta(days=TREND_DAYS - 1)
    start = datetime.combine(start_day, datetime.min.time())

    baseline = await _count(db, select(func.count(Question.id)).where(scope, Question.created_at < start))
    day_col = func.date(Question.created_at)
    rows = await db.execute(
        select(day_col, func.count(Question.id))
        .where(scope, Question.created_at >= start)
        .group_by(day_col)
    )
    per_day: Dict[date, int] = {}
    for day, n in rows.all():
        d = _as_date(day)
        if d is not None:
            per_day[d] = per_day.get(d, 0) + int(n)

    points: List[TrendPoint] = []
    running = baseline
    for i in range(TREND_DAYS):
        d = start_day + timedelta(days=i)
        created = per_day.get(d, 0)
        running += created
        points.append(TrendPoint(date=d.isoformat(), created=created, total=running))
    return points


async def get_dashboard_stats(db: AsyncSession, *, subject_id: int, viewer: User) -> DashboardStats:
    now = datetime.utcnow()
    scope = _question_scope(subject_id, viewer)
    return DashboardStats(
        subject_id=subject_id,
        overview=await _overview(db, subject_id, viewer, scope, now),
        distribution=await _distribution(db, scope),
        knowledge_coverage=await _knowledge_coverage(db, subject_id, scope),
        trend=await _trend(db, scope, now),
    )


async def get_contributors(
    db: AsyncSession, *, subject_id: int, viewer: User, days: int
) -> DashboardContributors:
    since = datetime.utcnow() - timedelta(days=days)
    scope = _question_scope(subject_id, viewer)

    created_rows = await db.execute(
        select(Question.created_by, func.count(Question.id))
        .where(scope, Question.created_by.is_not(None), Question.created_at >= since)
        .group_by(Question.created_by)
    )
    reviewed_rows = await db.execute(
        select(ActivityLog.user_id, func.count(ActivityLog.id))
        .join(Question, Question.id == ActivityLog.resource_id)
        .where(
            scope,
            ActivityLog.action == "review",
            ActivityLog.resource_type == "question",
            ActivityLog.user_id.is_not(None),
            ActivityLog.created_at >= since,
        )
        .group_by(ActivityLog.user_id)
    )

    stats: Dict[int, Dict[str, int]] = {}
    for uid, n in created_rows.all():
        stats.setdefault(uid, {"created": 0, "reviewed": 0})["created"] = int(n)
    for uid, n in reviewed_rows.all():
        stats.setdefault(uid, {"created": 0, "reviewed": 0})["reviewed"] = int(n)

    items: List[Contributor] = []
    if stats:
        users = (await db.execute(select(User).where(User.id.in_(stats.keys())))).scalars().all()
        for u in users:
            s = stats[u.id]
            items.append(
                Contributor(
                    user_id=u.id,
                    username=u.username,
                    full_name=u.full_name,
                    avatar_url=u.avatar_url,
                    created=s["created"],
                    reviewed=s["reviewed"],
                )
            )
    items.sort(key=lambda c: (-(c.created + c.reviewed), -c.created, c.user_id))
    return DashboardContributors(subject_id=subject_id, days=days, items=items[:CONTRIBUTOR_LIMIT])
