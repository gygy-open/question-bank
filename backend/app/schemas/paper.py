from pydantic import BaseModel
from typing import List, Optional
from enum import Enum

class OutputFormat(str, Enum):
    DOCX = "docx"
    LATEX = "latex"

class PaperGenerateRequest(BaseModel):
    title: str
    question_ids: List[int]
    format: OutputFormat = OutputFormat.DOCX
    include_answer: bool = True
    include_analysis: bool = True
    include_explanation: bool = True
    include_summary: bool = True
    include_source: bool = False
