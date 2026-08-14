from typing import Optional

from pydantic import BaseModel


class SubjectPromptUpdate(BaseModel):
    value: str


class SubjectPromptOut(BaseModel):
    key: str
    title: str
    description: str
    default: str  # 代码默认模板（含占位符），供 UI 预览 / "基于默认创建副本"
    value: Optional[str] = None  # 科目覆盖原文；None 表示未定制、当前使用默认
    is_custom: bool
