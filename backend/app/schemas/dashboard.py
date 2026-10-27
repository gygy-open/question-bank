from typing import List, Optional

from pydantic import BaseModel


class DashboardOverview(BaseModel):
    total_questions: int
    new_questions_7d: int
    published: int
    pending: int
    stimuli: int
    compositions: int
    knowledge_points: int
    tags: int


class CountItem(BaseModel):
    key: str
    count: int


class DashboardDistribution(BaseModel):
    q_type: List[CountItem]
    status: List[CountItem]
    difficulty: List[CountItem]
    visibility: List[CountItem]


class KnowledgePointCount(BaseModel):
    id: int
    name: str
    count: int


class DashboardKnowledgeCoverage(BaseModel):
    total: int
    covered: int
    top: List[KnowledgePointCount]
    uncovered: List[KnowledgePointCount]
    questions_without_kp: int
    questions_without_tag: int


class TrendPoint(BaseModel):
    date: str
    created: int
    total: int


class DashboardStats(BaseModel):
    subject_id: int
    overview: DashboardOverview
    distribution: DashboardDistribution
    knowledge_coverage: DashboardKnowledgeCoverage
    trend: List[TrendPoint]


class Contributor(BaseModel):
    user_id: int
    username: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    created: int
    reviewed: int


class DashboardContributors(BaseModel):
    subject_id: int
    days: int
    items: List[Contributor]
