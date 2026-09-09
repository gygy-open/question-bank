"""领域错误 —— 与传输层无关的失败语义。

Capability / 领域服务只抛这些;由适配器负责翻译:
- API 适配器 → HTTP 状态码(`app.main` 里注册的 exception handler)
- Tool 适配器 → 结构化 ToolResult,回喂模型让它自我纠正

detail 文案会原样出现在 HTTP 响应体的 `detail` 字段,改动等于改对外契约。
"""
from __future__ import annotations


class DomainError(Exception):
    """所有领域错误的基类。"""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class NotFound(DomainError):
    """资源不存在,或对调用者不可见(跨 subject/scope/owner 时用它防枚举)。"""


class Forbidden(DomainError):
    """已定位到资源,但调用者无权执行该动作。"""


class Invalid(DomainError):
    """请求结构非法(自引用、成环、AST 违规)。"""


class Conflict(DomainError):
    """与当前状态冲突(乐观锁 revision 不匹配、删除非空目录)。"""


class Unprocessable(DomainError):
    """语义上无法处理(引用的题目缺失、跨学科引用)。"""


# 单点映射表。新增 DomainError 子类必须在这里登记,否则 handler 会退化成 500。
DOMAIN_ERROR_STATUS: dict[type[DomainError], int] = {
    NotFound: 404,
    Forbidden: 403,
    Invalid: 400,
    Conflict: 409,
    Unprocessable: 422,
}


def status_for(error: DomainError) -> int:
    for klass in type(error).__mro__:
        if klass in DOMAIN_ERROR_STATUS:
            return DOMAIN_ERROR_STATUS[klass]
    return 500
