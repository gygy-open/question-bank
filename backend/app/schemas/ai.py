from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Optional, Union, Any, Dict, Iterator

class QuestionTypeEnum(str, Enum):
    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"
    FILL_IN_THE_BLANK = "fill_in_the_blank"
    FREE_RESPONSE = "free_response"

class AIQuestion(BaseModel):
    id: Optional[str] = None
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
    parent_id: Optional[str] = None
    children: Optional[List['AIQuestion']] = None


class AIStimulus(BaseModel):
    temp_id: Optional[str] = None
    markdown: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AIQuestionGroup(BaseModel):
    temp_id: Optional[str] = None
    stimulus_temp_id: str
    question_temp_ids: List[str]
    metadata: Dict[str, Any] = Field(default_factory=dict)


class QuestionList(BaseModel):
    questions: List[AIQuestion]
    stimuli: List[AIStimulus] = Field(default_factory=list)
    question_groups: List[AIQuestionGroup] = Field(default_factory=list)
    paper: Optional[Dict[str, Any]] = None

    def __len__(self) -> int:
        return len(self.questions)

    def __iter__(self) -> Iterator[AIQuestion]:
        return iter(self.questions)

    def __getitem__(self, index: int) -> AIQuestion:
        return self.questions[index]
