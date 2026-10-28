from .base import Base
from .user import User
from .api_key import ApiKey
from .subject import Subject
from .subject_member import SubjectMember
from .knowledge_point import KnowledgePoint
from .tag import Tag
from .tag_category import TagCategory
from .question import Question, QuestionDedupBand
from .stimulus import Stimulus
from .question_relation import QuestionRelation
from .question_relation_audit import LegacyQuestionParentAudit
from .import_task import ImportTask
from .media_asset import LegacyMediaPath, MediaAsset, MediaReference
from .activity_log import ActivityLog
from .system_setting import SystemSetting
from .subject_prompt import SubjectPrompt
from .subject_setting import SubjectSetting
from .ai_config import AIProvider, AIModel, UserAIPreference
from .chat import ChatSession, ChatMessage
from .agent import AgentRun, AgentStep
from .prompt import PromptTemplate
from .paper import Paper, PaperQuestion
from .composition import (
    ScopeType,
    CompositionStatus,
    CompositionNodeKind,
    Folder,
    Composition,
    CompositionNode,
    CompositionVersion,
    CompositionEvent,
)

# 题目查重签名的 flush 钩子:随模型一起加载,保证任何写入路径都会维护签名。
from app.services import question_dedup as _question_dedup  # noqa: E402,F401
