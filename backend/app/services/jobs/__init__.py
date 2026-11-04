"""通用后台任务:jobs 表的服务层、处理器注册表与执行器。

- ``service``:入队、领取、状态流转、暂停 / 恢复、取消、删除(不含执行逻辑);
- ``registry``:``JobHandler`` 接口与按任务类型的注册表;
- ``runner``:``run_job`` 执行一条 job,``JobContext`` 供处理器汇报进度与结果。
"""
from . import service as job_service
from .registry import JobHandler, get_handler, load_handlers, register_handler, registered_types
from .runner import (
    CANCEL_POLL_SECONDS,
    JobContext,
    JobStopped,
    ProviderBreaker,
    dump_progress,
    run_job,
)

__all__ = [
    "CANCEL_POLL_SECONDS",
    "JobContext",
    "JobHandler",
    "JobStopped",
    "ProviderBreaker",
    "dump_progress",
    "get_handler",
    "job_service",
    "load_handlers",
    "register_handler",
    "registered_types",
    "run_job",
]
