"""桌面版:导入识别完成/失败/暂停时弹系统通知。

在托盘进程里用独立线程和独立的数据库连接轮询导入任务,不依赖浏览器页面是否打开。
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, List, Optional, Set, Tuple

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.import_task import ImportTask, ImportTaskStatus

logger = logging.getLogger(__name__)

POLL_SECONDS = 10.0
# 同一轮里待审核的导入超过这个数就合并成一条通知。
_MAX_SEPARATE = 3


@dataclass
class NotifierState:
    since: datetime = field(default_factory=datetime.utcnow)
    seen: Set[Tuple[int, str]] = field(default_factory=set)


def _count(task: ImportTask) -> int:
    try:
        return int(json.loads(task.progress or "{}").get("count") or 0)
    except (ValueError, TypeError):
        return 0


async def poll_once(
    sessionmaker: Callable[[], AsyncSession], state: NotifierState, tr: Callable[..., str]
) -> List[str]:
    """返回自上次轮询以来需要提示的消息,并推进 state。"""
    async with sessionmaker() as session:
        rows = (
            await session.execute(
                select(ImportTask)
                .where(
                    ImportTask.updated_at >= state.since,
                    or_(
                        ImportTask.status.in_(
                            [ImportTaskStatus.REVIEW_READY, ImportTaskStatus.FAILED, ImportTaskStatus.PAUSED]
                        ),
                        (ImportTask.status == ImportTaskStatus.COMPLETED) & ImportTask.auto_commit.is_(True),
                    ),
                )
                .order_by(ImportTask.updated_at)
            )
        ).scalars().all()

    ready: List[ImportTask] = []
    messages: List[str] = []
    paused = 0
    for task in rows:
        status = task.status.value if isinstance(task.status, ImportTaskStatus) else str(task.status)
        key = (task.id, status)
        if task.updated_at and task.updated_at > state.since:
            state.since = task.updated_at
        if key in state.seen:
            continue
        state.seen.add(key)
        if status == ImportTaskStatus.REVIEW_READY.value:
            ready.append(task)
        elif status == ImportTaskStatus.COMPLETED.value:
            messages.append(tr("notify.import_saved", name=task.original_filename, count=_count(task)))
        elif status == ImportTaskStatus.FAILED.value:
            messages.append(tr("notify.import_failed", name=task.original_filename))
        else:
            paused += 1

    if len(ready) > _MAX_SEPARATE:
        messages.insert(0, tr("notify.imports_ready_many", count=len(ready)))
    else:
        messages[:0] = [
            tr("notify.import_ready", name=task.original_filename, count=_count(task)) for task in ready
        ]
    if paused:
        messages.append(tr("notify.imports_paused", count=paused))
    return messages


class ImportNotifier:
    """后台线程:定期轮询并调用 notify;任何错误都只记日志,不影响托盘。"""

    def __init__(self, notify: Callable[[str], None], tr: Callable[..., str], *, interval: float = POLL_SECONDS) -> None:
        self._notify = notify
        self._tr = tr
        self._interval = interval
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="import-notifier", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        try:
            asyncio.run(self._loop())
        except Exception:  # noqa: BLE001 - 通知是锦上添花
            logger.warning("Import notifier stopped", exc_info=True)

    async def _loop(self) -> None:
        from app.core.config import get_db_url
        from app.db.session import _apply_sqlite_pragmas, _build_engine_kwargs

        url = get_db_url()
        if not url:
            return
        engine = create_async_engine(url, **_build_engine_kwargs(url))
        if url.startswith("sqlite"):
            _apply_sqlite_pragmas(engine)
        maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
        state = NotifierState()
        try:
            while not self._stop.is_set():
                await asyncio.sleep(self._interval)
                try:
                    for message in await poll_once(maker, state, self._tr):
                        self._notify(message)
                except Exception:  # noqa: BLE001 - 表还没建好等情况,下一轮再试
                    logger.debug("Import notifier poll failed", exc_info=True)
        finally:
            await engine.dispose()
