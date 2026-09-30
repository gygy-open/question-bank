"""媒体回收:删除没有任何记录引用的对象文件,以及已软删除且不再被引用的资产行。

对象先写盘、后提交数据库(上传、同步导入等待用户确认),因此只回收超过宽限期的对象。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.models.import_task import ImportTask
from app.models.media_asset import LegacyMediaPath, MediaAsset, MediaReference

DEFAULT_GRACE_DAYS = 7


@dataclass
class GcReport:
    orphan_objects: list[Path] = field(default_factory=list)
    orphan_bytes: int = 0
    deleted_assets: list[int] = field(default_factory=list)
    stale_tmp_removed: int = 0

    def lines(self) -> list[str]:
        return [
            f"无引用的对象文件: {len(self.orphan_objects)}（{self.orphan_bytes / 1024 / 1024:.1f} MB）",
            f"已软删除且无引用的资产行: {len(self.deleted_assets)}",
            f"清理的临时目录/暂存文件: {self.stale_tmp_removed}",
        ]


async def _referenced_hashes(db: AsyncSession) -> set[str]:
    hashes: set[str] = set()
    hashes.update(await db.scalars(select(MediaAsset.sha256)))
    hashes.update(await db.scalars(select(LegacyMediaPath.sha256)))
    hashes.update(await db.scalars(select(ImportTask.source_sha256).where(ImportTask.source_sha256.is_not(None))))
    return hashes


async def collect_garbage(db: AsyncSession, *, apply: bool, grace_days: int = DEFAULT_GRACE_DAYS) -> GcReport:
    """dry-run 同样在事务内删资产行以得到准确的对象回收量,最后回滚且不删任何文件。"""
    report = GcReport()

    # 先处理资产行:删掉的行不再持有对象,本轮即可一并回收对象。
    cutoff = datetime.utcnow() - timedelta(days=grace_days)
    referenced = exists().where(MediaReference.asset_id == MediaAsset.id)
    report.deleted_assets = list(
        await db.scalars(
            select(MediaAsset.id).where(
                MediaAsset.deleted_at.is_not(None),
                MediaAsset.deleted_at < cutoff,
                ~referenced,
            )
        )
    )
    if report.deleted_assets:
        await db.execute(delete(MediaAsset).where(MediaAsset.id.in_(report.deleted_assets)))
        await db.flush()

    keep = await _referenced_hashes(db)
    mtime_cutoff = time.time() - grace_days * 86400
    for sha, path in storage.iter_objects():
        if sha in keep:
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        if stat.st_mtime >= mtime_cutoff:
            continue
        report.orphan_objects.append(path)
        report.orphan_bytes += stat.st_size

    if not apply:
        await db.rollback()
        return report
    await db.commit()
    for path in report.orphan_objects:
        path.unlink(missing_ok=True)
    report.stale_tmp_removed = storage.cleanup_stale_tmp()
    return report
