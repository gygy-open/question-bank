from pydantic import BaseModel, field_validator, model_validator
from typing import Optional, List, Any, Dict
import json
from datetime import datetime
from app.models.question import QuestionType, QuestionStatus
from .tag import Tag
from .knowledge_point import KnowledgePoint
from .user import User
from .activity_log import ActivityLog
from .subject import Subject
from .import_task import ImportTask

class QuestionBase(BaseModel):
    content: str
    options: Optional[List[Dict[str, Any]]] = None
    answer: Optional[str] = None
    thinking: Optional[str] = None
    analysis: Optional[str] = None
    summary: Optional[str] = None
    q_type: QuestionType
    status: QuestionStatus = QuestionStatus.PUBLISHED
    difficulty: int = 1
    source: Optional[str] = None
    parent_id: Optional[int] = None

    @field_validator('options', mode='before')
    @classmethod
    def parse_options(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, list):
            new_options = []
            for i, item in enumerate(v):
                if isinstance(item, str):
                    # Convert string "A. content" to dict
                    parts = item.split(".", 1)
                    if len(parts) == 2 and len(parts[0]) <= 3:
                        label = parts[0].strip()
                        content = parts[1].strip()
                        new_options.append({"label": label, "content": content})
                    else:
                        label = chr(65 + i) if i < 26 else str(i+1)
                        new_options.append({"label": label, "content": item})
                else:
                    new_options.append(item)
            return new_options
        return v

class QuestionCreate(QuestionBase):
    knowledge_point_ids: List[int] = []
    tag_ids: Optional[List[int]] = []
    import_task_id: Optional[int] = None
    subject_id: Optional[int] = None
    ai_suggested_tags: Optional[Dict[str, List[str]]] = None
    children: Optional[List['QuestionCreate']] = None
    temp_id: Optional[str] = None
    
    # Override parent_id to allow string UUIDs during creation/import
    parent_id: Optional[Any] = None
    
    @model_validator(mode='after')
    def validate_answer_format(self) -> 'QuestionCreate':
        """Validate answer format for fill-in-the-blank questions on creation"""
        if self.q_type == QuestionType.FILL_IN_THE_BLANK and self.answer:
            try:
                parsed = json.loads(self.answer)
                if not isinstance(parsed, list):
                    raise ValueError("Answer for fill-in-the-blank must be a JSON list")
                # Optional: Validate inner structure List[List[str]]
                for item in parsed:
                    if not isinstance(item, list):
                         # If it's not a list of lists, it might be a simple list of answers. 
                         # We could enforce List[List[str]] but let's be lenient or just check it's a list.
                         pass
            except json.JSONDecodeError:
                raise ValueError("Answer for fill-in-the-blank must be a valid JSON string")
        return self

class QuestionBatchCreate(BaseModel):
    filename: Optional[str] = None
    file_path: Optional[str] = None
    questions: List[QuestionCreate]

class QuestionUpdate(QuestionBase):
    content: Optional[str] = None
    answer: Optional[str] = None
    q_type: Optional[QuestionType] = None
    status: Optional[QuestionStatus] = None
    knowledge_point_ids: Optional[List[int]] = None
    tag_ids: Optional[List[int]] = None
    subject_id: Optional[int] = None
    
    @model_validator(mode='after')
    def validate_answer_format(self) -> 'QuestionUpdate':
        """Validate answer format for fill-in-the-blank questions on update"""
        if self.q_type == QuestionType.FILL_IN_THE_BLANK and self.answer:
            try:
                parsed = json.loads(self.answer)
                if not isinstance(parsed, list):
                    raise ValueError("Answer for fill-in-the-blank must be a JSON list")
                for item in parsed:
                    if not isinstance(item, list):
                         pass
            except json.JSONDecodeError:
                raise ValueError("Answer for fill-in-the-blank must be a valid JSON string")
        return self

class QuestionReview(BaseModel):
    status: QuestionStatus
    comment: Optional[str] = None

class QuestionSummary(QuestionBase):
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class Question(QuestionBase):
    id: int
    import_task_id: Optional[int] = None
    subject_id: Optional[int] = None
    knowledge_points: List[KnowledgePoint] = []
    created_at: datetime
    updated_at: datetime
    tags: List[Tag] = []
    
    review_count: int = 0
    creator: Optional[User] = None
    updater: Optional[User] = None
    review_logs: List[ActivityLog] = []
    subject: Optional[Subject] = None
    import_task: Optional[ImportTask] = None
    children: Optional[List['Question']] = []
    parent: Optional['QuestionSummary'] = None

    @field_validator('review_count', mode='before')
    @classmethod
    def set_review_count_default(cls, v):
        return v or 0

    class Config:
        from_attributes = True

class QuestionPage(BaseModel):
    items: List[Question]
    total: int
    page: int
    size: int
    pages: int

class QuestionBatchConfirm(BaseModel):
    question_ids: List[int]
    action: str # "approve" or "reject"

class QuestionBatchDelete(BaseModel):
    ids: List[int]

class QuestionBatchUpdate(BaseModel):
    ids: List[int]
    source: Optional[str] = None

Question.model_rebuild()
