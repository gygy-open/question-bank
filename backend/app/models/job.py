"""通用后台任务表 ``jobs``:所有需要排队执行的后台工作共用一套调度与执行状态。

设计要点
--------
1. **执行状态集中在这里,业务状态留在业务表。**
   一条 job 只回答「它排没排上、跑没跑、跑得怎样」:待执行 / 执行中 / 暂停 / 成功 /
   失败 / 取消。它服务的业务记录(导入任务、题干拆解……)通过 ``target_type`` +
   ``target_id`` 指回去;「待审核」「已入库」这类执行结束之后才有意义的状态,由
   业务表自己保存。
2. **worker 只认识 jobs。** 领取、优先级、重试、按 AI 服务商暂停与恢复、熔断、
   取消、重启后重新入队,全部只在 ``app/services/jobs`` 实现一次;不同任务类型只
   需要注册一个处理器(handler)。
3. **状态用字符串而不是数据库 ENUM。** 与 ``subject_members.role`` 一致:取值在应用
   层校验,将来增加状态或任务类型不需要迁移。
4. **target 是多态引用,不设外键。** 一张 jobs 表要服务多种业务表,无法对单一表建
   外键;业务记录删除时由业务代码顺带删除它的 job(见 ``job_service.delete_for_target``)。
"""

import enum
from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Integer, String, Text

from .base import Base


class JobStatus(str, enum.Enum):
    """job 的执行状态。只描述执行过程,不承载任何业务含义。"""

    # 排队等待 worker 领取。
    PENDING = "pending"
    # 已被 worker 领取,正在执行。
    RUNNING = "running"
    # AI 服务不可用(额度/鉴权/模型/不可达)时暂停;恢复后回到 PENDING。
    PAUSED = "paused"
    # 执行完成(业务结果由处理器写进业务表)。
    SUCCEEDED = "succeeded"
    # 执行失败,不会自动重试。
    FAILED = "failed"
    # 被用户取消或其业务记录被放弃。
    CANCELLED = "cancelled"


# 仍在队列里、尚未结束的状态。
ACTIVE_JOB_STATUSES = (JobStatus.PENDING.value, JobStatus.RUNNING.value, JobStatus.PAUSED.value)


class JobPriority:
    """优先级:数值越大越先执行。

    用户手动触发的工作要立刻有反馈,入库后自动触发的次之,存量回填排最后,
    避免成千上万条回填任务堵住用户的导入。
    """

    USER = 100
    AUTO = 50
    BACKFILL = 10


class Job(Base):
    """一条后台任务。"""

    __tablename__ = "jobs"
    __table_args__ = (
        # worker 领取:WHERE status='pending' ORDER BY priority DESC, created_at, id
        Index("ix_jobs_status_priority_created", "status", "priority", "created_at"),
        # 按业务记录反查它的 job(取消、删除、展示进度)。
        Index("ix_jobs_target", "target_type", "target_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    # 任务类型,例如 import.extract / structure.decompose;决定由哪个处理器执行。
    type = Column(String(64), nullable=False, index=True)
    # 取值见 JobStatus。
    status = Column(String(16), nullable=False, default=JobStatus.PENDING.value)
    # 取值见 JobPriority,数值越大越先执行。
    priority = Column(Integer, nullable=False, default=JobPriority.USER)

    # 已执行次数(每次被领取 +1)与上限;超过上限的失败不再自动重试。
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=1)
    # 不早于这个时间才允许被领取;为空表示随时可以。
    run_after = Column(DateTime, nullable=True)

    # 业务记录的多态引用,例如 ("import_task", 12)、("question", 345)。
    target_type = Column(String(32), nullable=True)
    target_id = Column(Integer, nullable=True)

    # 最近一次执行所用 / 出错的 AI 服务商;暂停与恢复按它分组。
    provider_id = Column(Integer, nullable=True, index=True)
    # 暂停原因:quota / auth / model / unavailable(与 ImportPauseReason 取值一致)。
    paused_reason = Column(String(20), nullable=True)
    # 最近一次失败或暂停的错误信息。
    error = Column(Text, nullable=True)
    # 进度(JSON 字符串),结构由处理器决定,例如 {"stage": "extracting"}。
    progress = Column(Text, nullable=True)
    # 处理器需要的参数(JSON 字符串)。
    payload = Column(Text, nullable=True)

    # 发起人、所属学科与界面语言:处理器据此选择 AI 模型、做权限判断、输出对应语言。
    user_id = Column(Integer, nullable=True, index=True)
    subject_id = Column(Integer, nullable=True)
    locale = Column(String(16), nullable=True)

    # 幂等键:同一个键只会创建一条 job(例如“同一道题的同一次拆解请求”)。
    idempotency_key = Column(String(128), nullable=True, unique=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
