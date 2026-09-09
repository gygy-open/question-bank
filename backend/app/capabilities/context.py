"""能力执行上下文 —— 「谁、在哪个学科、从哪个入口」调用。

同一个 Capability 被 HTTP 端点、AI 工具、后台 worker 调用时,差异全部收敛到这里,
业务代码不感知调用方。
"""
from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class Surface(str, enum.Enum):
    """调用入口。MCP 尚未实现,等接入时再加值。"""
    API = "api"
    CHAT = "chat"
    WORKER = "worker"


@dataclass(frozen=True)
class ExecutionContext:
    db: AsyncSession
    actor: User  # 必须已 selectinload subject_memberships(见 deps.get_current_user)
    surface: Surface
    subject_id: int | None = None
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    dry_run: bool = False  # 预留:返回 diff 不落库,当前无能力实现该分支

    def with_subject(self, subject_id: int | None) -> "ExecutionContext":
        """能力在解析出真实 subject 后据此鉴权(如 update 要用实体自身的 subject_id)。"""
        return ExecutionContext(
            db=self.db,
            actor=self.actor,
            surface=self.surface,
            subject_id=subject_id,
            request_id=self.request_id,
            dry_run=self.dry_run,
        )
