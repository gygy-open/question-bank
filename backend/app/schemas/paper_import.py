"""整卷导入(题目 + 可复用稿件)的请求/响应契约。

题目本身沿用严格 v2 的 `QuestionCreate`;整卷结构走 outline,二者靠 temp_id 关联。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.question import QuestionStatus
from app.services.importing.contracts import OUTLINE_KINDS


class PaperOutlineItemInput(BaseModel):
    """版面项。字段按 kind 取用;未知 kind 直接拒绝,避免静默丢版面。"""

    kind: str
    text: Optional[str] = None
    level: Optional[int] = None
    markdown: Optional[str] = None
    reason: Optional[str] = None
    temp_id: Optional[str] = None
    number: Optional[str] = None
    score: Optional[float] = None
    lines: Optional[int] = None
    style: Optional[str] = None
    scope: Optional[str] = None
    fields: Optional[Dict[str, bool]] = None

    @model_validator(mode="after")
    def _check_kind(self) -> "PaperOutlineItemInput":
        if self.kind not in OUTLINE_KINDS:
            raise ValueError(f"unknown outline kind: {self.kind}")
        if self.kind == "question_ref" and not self.temp_id:
            raise ValueError("question_ref requires temp_id")
        return self


class PaperImportQuestion(BaseModel):
    """审核通过的题目 + 与 outline 对齐的临时 id。

    故意不继承严格的 `QuestionCreate`:若在请求解析阶段就逐题严格校验,一道坏题
    会让整批请求直接 422,用户永远没机会选择"仅用已成功的题目继续"。
    校验下沉到服务层逐题进行,失败者进 skipped。
    """

    model_config = ConfigDict(extra="allow")

    temp_id: Optional[str] = None
    parent_temp_id: Optional[str] = None


class PaperImportPreviewRequest(BaseModel):
    scope: str
    questions: List[PaperImportQuestion] = Field(default_factory=list)
    outline: List[PaperOutlineItemInput] = Field(default_factory=list)


class SkippedQuestionRead(BaseModel):
    index: int
    temp_id: Optional[str] = None
    message: str


class DegradedItemRead(BaseModel):
    reason: str
    excerpt: str


class PaperImportPreviewResponse(BaseModel):
    importable_count: int
    skipped: List[SkippedQuestionRead] = Field(default_factory=list)
    degraded: List[DegradedItemRead] = Field(default_factory=list)
    blocking_reason: Optional[str] = None


class PaperImportCommitRequest(BaseModel):
    scope: str
    questions: List[PaperImportQuestion] = Field(default_factory=list)
    outline: List[PaperOutlineItemInput] = Field(default_factory=list)
    save_as_composition: bool = False
    title: Optional[str] = None
    folder_id: Optional[int] = None
    renumber: bool = False
    proceed_with_partial: bool = False
    status: QuestionStatus = QuestionStatus.PENDING
    filename: Optional[str] = None
    file_path: Optional[str] = None
    content_sha256: Optional[str] = None
    idempotency_key: Optional[str] = None

    @model_validator(mode="after")
    def _check_composition_fields(self) -> "PaperImportCommitRequest":
        if self.save_as_composition and not (self.title or "").strip():
            raise ValueError("保存为稿件时必须提供稿件名称")
        return self


class PaperImportCommitResponse(BaseModel):
    import_task_id: int
    created_count: int
    created_question_ids: List[int] = Field(default_factory=list)
    skipped: List[SkippedQuestionRead] = Field(default_factory=list)
    degraded: List[DegradedItemRead] = Field(default_factory=list)
    composition_id: Optional[int] = None
    composition_title: Optional[str] = None
    temp_id_map: Dict[str, int] = Field(default_factory=dict)
    reused_existing: bool = False


class DuplicateUploadRead(BaseModel):
    """文件内容完全一致的历史导入;仅提示,不阻塞。"""

    import_task_id: int
    original_filename: Optional[str] = None
    imported_at: Optional[Any] = None
    composition_id: Optional[int] = None
