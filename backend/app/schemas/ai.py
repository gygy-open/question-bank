from enum import Enum
from pydantic import BaseModel
from typing import List, Optional, Union, Any

class QuestionTypeEnum(str, Enum):
    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"
    FILL_IN_THE_BLANK = "fill_in_the_blank"
    FREE_RESPONSE = "free_response"

class AIQuestion(BaseModel):
    q_type: QuestionTypeEnum # Renamed from type to match database and prompt
    content: str
    options: Optional[List[str]] = None
    # Allow structured answer for fill-in-the-blank (List[List[str]]) or string for others
    answer: Optional[Union[str, List[List[str]], Any]] = None 
    thinking: Optional[str] = None
    analysis: Optional[str] = None
    summary: Optional[str] = None
    difficulty: Optional[int] = None
    knowledge_points: Optional[List[str]] = None
    knowledge_point_ids: Optional[List[int]] = None
    tags: Optional[List[str]] = None


class QuestionList(BaseModel):
    questions: List[AIQuestion]
