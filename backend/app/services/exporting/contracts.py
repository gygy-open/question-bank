"""导出共享契约:渲染器无关的选项结构。

`ExportOption` 与 `RichDoc` 被答案格式化(answer.py)与组稿导出(composition_contracts.py)复用。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

# RichDoc:一个 Tiptap doc(dict)或空。
RichDoc = Optional[dict[str, Any]]


@dataclass
class ExportOption:
    id: str
    label: str
    content: RichDoc
