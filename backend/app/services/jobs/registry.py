"""任务处理器(handler)的接口与注册表。

每种任务类型(``Job.type``)对应一个处理器。worker 领取到 job 后按类型找到处理器
执行;job_service 在执行状态变化时调用处理器的 ``project``,把状态同步到业务表。

新增一种后台任务只需要:
1. 继承 ``JobHandler``,实现 ``run``(必要时实现 ``ai_purpose`` / ``project``);
2. 用 ``@register_handler`` 装饰;
3. 把模块路径加进 ``_HANDLER_MODULES``,让 worker / API 进程都能加载到。
"""
from __future__ import annotations

import importlib
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar, Dict, Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job, JobStatus

if TYPE_CHECKING:  # pragma: no cover - 仅用于类型标注,避免循环导入
    from .runner import JobContext

# 定义了处理器的模块。注册发生在模块导入时,这里集中列出,保证任何进程(worker、
# API、测试)第一次查找处理器前都已全部注册。
_HANDLER_MODULES = (
    "app.services.importing.job",
    "app.services.structure.job",
)

_HANDLERS: Dict[str, "JobHandler"] = {}
_loaded = False


class JobHandler(ABC):
    """一种后台任务的执行逻辑。

    处理器是无状态单例:同一个实例会被并发地用于多条 job,所有运行时状态都放在
    ``JobContext`` 里。
    """

    # 任务类型,与 Job.type 一致,例如 "import.extract"。
    type: ClassVar[str]
    # 该类型 job 的 target_type,例如 "import_task";没有业务记录时为 None。
    target_type: ClassVar[Optional[str]] = None

    # region 公共接口

    @abstractmethod
    async def run(self, ctx: "JobContext") -> None:
        """执行任务。

        约定:
        - 正常返回而没有显式调用 ``ctx.succeed`` 时,runner 会把 job 记为成功;
        - 需要失败/暂停时调用 ``ctx.fail`` / ``ctx.pause`` / ``ctx.handle_ai_error`` 后直接返回;
        - 任何未捕获的异常都会被 runner 记为失败。
        """

    async def ai_purpose(self, db: AsyncSession, job: Job) -> Optional[str]:
        """该 job 需要的 AI 用途("text" / "vision"),不需要 AI 时返回 None。

        某个 AI 服务商出故障时,job_service 用它找出「排队中、也会用到同一服务商」
        的其他 job 一起暂停,避免它们挨个撞同一堵墙。默认认为需要文本模型。
        """
        return "text"

    async def project(
        self,
        db: AsyncSession,
        target_ids: Sequence[int],
        status: JobStatus,
        **values: Any,
    ) -> None:
        """把 job 的执行状态同步(投影)到业务表。默认不做任何事。

        :param target_ids: 状态发生变化的 job 所指向的业务记录 id。
        :param status: 新的执行状态。
        :param values: 随状态一起变化的信息:``error``、``paused_reason``、
            ``provider_id``、``progress``(JSON 字符串)。只包含本次真正变化的键。

        只能写入、不能提交;调用方(job_service)负责事务。
        """
        return None

    # endregion


# region 注册与查找

def register_handler(cls: type[JobHandler]) -> type[JobHandler]:
    """类装饰器:实例化并登记处理器。同一类型重复注册会在导入期直接报错。"""
    handler = cls()
    if handler.type in _HANDLERS:
        raise RuntimeError(f"Duplicate job handler for type: {handler.type}")
    _HANDLERS[handler.type] = handler
    return cls


def get_handler(job_type: str) -> Optional[JobHandler]:
    """按任务类型取处理器;未知类型返回 None(例如旧版本遗留的 job)。"""
    load_handlers()
    return _HANDLERS.get(job_type)


def registered_types() -> tuple[str, ...]:
    """当前进程已注册的全部任务类型;worker 只领取这些类型的 job。"""
    load_handlers()
    return tuple(_HANDLERS)


def load_handlers() -> None:
    """导入所有处理器模块(只做一次)。"""
    global _loaded
    if _loaded:
        return
    _loaded = True
    for module in _HANDLER_MODULES:
        importlib.import_module(module)

# endregion
