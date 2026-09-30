"""P3 存量迁移:把旧 /static/media 图片与 uploads 源文件搬进内容寻址存储。

- 题目 / 材料 / 稿件节点:图片节点补 assetId(保留原 src),登记引用;不改 updated_at。
- 定稿快照不改写,只登记引用与旧 URL 映射。
- 头像、对话附图:只登记旧 URL 映射,由 /static/media 鉴权路由继续下发。
- 导入任务:旧 uploads 源文件存入对象存储并回填 source_sha256。

幂等:已映射的旧路径、已有 assetId 的节点、已有 source_sha256 的任务都会跳过。
dry-run 在同一事务内执行后回滚;对象文件可能已预先写入(内容寻址,正式运行复用,否则由 GC 回收)。
"""
from __future__ import annotations

import asyncio
import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.capabilities.errors import Unprocessable
from app.core import storage
from app.core.config import settings
from app.core.file_paths import import_source_file
from app.models.chat import ChatMessage
from app.models.composition import Composition, CompositionNode, CompositionVersion
from app.models.import_task import ImportTask
from app.models.media_asset import LegacyMediaPath, MediaAsset, MediaOwnerType, MediaPurpose
from app.models.question import Question
from app.models.stimulus import Stimulus
from app.models.user import User
from app.services import media_refs, media_service
from app.services.question_content import parse_json_field, to_db_json

_QUESTION_STRING_FIELDS = ("content", "answer", "thinking", "analysis", "summary")


@dataclass
class MigrationReport:
    legacy_paths_mapped: int = 0
    assets_created: int = 0
    questions_updated: int = 0
    stimuli_updated: int = 0
    nodes_updated: int = 0
    versions_indexed: int = 0
    import_sources_stored: int = 0
    missing: set[str] = field(default_factory=set)
    unreadable: set[str] = field(default_factory=set)
    skipped: list[str] = field(default_factory=list)

    def lines(self) -> list[str]:
        out = [
            f"旧 URL 映射新增: {self.legacy_paths_mapped}",
            f"新建内容资产: {self.assets_created}",
            f"补 assetId 的题目: {self.questions_updated}",
            f"补 assetId 的材料: {self.stimuli_updated}",
            f"补 assetId 的稿件节点: {self.nodes_updated}",
            f"登记引用的定稿版本: {self.versions_indexed}",
            f"入库的导入源文件: {self.import_sources_stored}",
            f"文件缺失的旧 URL: {len(self.missing)}",
            f"无法识别格式的旧文件: {len(self.unreadable)}",
            f"跳过: {len(self.skipped)}",
        ]
        out += [f"  缺失 {p}" for p in sorted(self.missing)]
        out += [f"  无法识别 {p}" for p in sorted(self.unreadable)]
        out += [f"  跳过 {s}" for s in self.skipped]
        return out


class _Migrator:
    def __init__(self, db: AsyncSession, report: MigrationReport) -> None:
        self.db = db
        self.report = report
        self._legacy: dict[str, Optional[tuple[str, str, bytes]]] = {}
        self._assets: dict[tuple[int, str], Optional[int]] = {}

    async def _legacy_file(self, path: str) -> Optional[tuple[str, str, bytes]]:
        """旧 URL → (sha256, mime, bytes),并登记映射;文件缺失或无法识别返回 None。"""
        if path in self._legacy:
            return self._legacy[path]
        result: Optional[tuple[str, str, bytes]] = None
        existing = await self.db.scalar(select(LegacyMediaPath).where(LegacyMediaPath.old_path == path))
        if existing is not None and storage.exists(existing.sha256):
            data = await asyncio.to_thread(storage.read_bytes, existing.sha256)
            result = (existing.sha256, existing.mime, data)
        else:
            real = media_service.legacy_media_file(path)
            if real is None:
                self.report.missing.add(path)
            else:
                data = await asyncio.to_thread(real.read_bytes)
                try:
                    mime = media_service.sniff(data, allow_legacy_formats=True).mime
                except Unprocessable:
                    self.report.unreadable.add(path)
                else:
                    sha = await asyncio.to_thread(storage.put_bytes, data)
                    if existing is None:
                        self.db.add(LegacyMediaPath(old_path=path, sha256=sha, mime=mime))
                        self.report.legacy_paths_mapped += 1
                    result = (sha, mime, data)
        self._legacy[path] = result
        return result

    async def asset_for(self, subject_id: int, path: str) -> Optional[int]:
        key = (subject_id, path)
        if key in self._assets:
            return self._assets[key]
        legacy = await self._legacy_file(path)
        asset_id: Optional[int] = None
        if legacy is not None:
            sha, _, data = legacy
            existed = await self.db.scalar(
                select(MediaAsset.id).where(
                    MediaAsset.purpose == MediaPurpose.CONTENT.value,
                    MediaAsset.subject_id == subject_id,
                    MediaAsset.sha256 == sha,
                )
            )
            asset = await media_service.ingest(
                self.db,
                data,
                purpose=MediaPurpose.CONTENT,
                actor_id=None,
                subject_id=subject_id,
                filename=os.path.basename(path),
                allow_legacy_formats=True,
                max_bytes=max(len(data), 1),
            )
            if existed is None:
                asset.source = "migration"
                self.report.assets_created += 1
            asset_id = asset.id
        self._assets[key] = asset_id
        return asset_id

    async def link_images(self, value: Any, subject_id: int) -> bool:
        """就地给 value 中的旧图片节点补 assetId;有改动返回 True。"""
        changed = False
        for attrs in media_service.iter_image_attrs(value):
            if attrs.get("assetId"):
                continue
            path = media_service.normalize_legacy_path(attrs.get("src"))
            if path is None:
                continue
            asset_id = await self.asset_for(subject_id, path)
            if asset_id is not None:
                attrs["assetId"] = asset_id
                changed = True
        return changed


async def _migrate_questions(m: _Migrator) -> None:
    rows = (await m.db.execute(select(Question.id, Question.subject_id, *(
        getattr(Question, f) for f in (*_QUESTION_STRING_FIELDS, "options")
    )))).all()
    for row in rows:
        values = {f: parse_json_field(getattr(row, f)) for f in _QUESTION_STRING_FIELDS}
        values["options"] = row.options
        if not any(media_service.collect_legacy_paths(v) for v in values.values()):
            continue
        if row.subject_id is None:
            m.report.skipped.append(f"题目 #{row.id} 没有学科")
            continue
        changed = [f for f, v in values.items() if await m.link_images(v, row.subject_id)]
        if changed:
            updates = {f: (values[f] if f == "options" else to_db_json(values[f])) for f in changed}
            await m.db.execute(
                update(Question).where(Question.id == row.id).values(**updates, updated_at=Question.updated_at)
            )
            m.report.questions_updated += 1
        await media_refs.sync_refs(
            m.db, MediaOwnerType.QUESTION, row.id, values.values(), subject_id=row.subject_id, validate=False
        )


async def _migrate_stimuli(m: _Migrator) -> None:
    rows = (await m.db.execute(select(Stimulus.id, Stimulus.subject_id, Stimulus.content))).all()
    for row in rows:
        content = parse_json_field(row.content)
        if not await m.link_images(content, row.subject_id):
            continue
        await m.db.execute(
            update(Stimulus)
            .where(Stimulus.id == row.id)
            .values(content=to_db_json(content), updated_at=Stimulus.updated_at)
        )
        m.report.stimuli_updated += 1
        await media_refs.sync_refs(
            m.db, MediaOwnerType.STIMULUS, row.id, [content], subject_id=row.subject_id, validate=False
        )


async def _migrate_compositions(m: _Migrator) -> None:
    rows = (await m.db.execute(
        select(CompositionNode.id, CompositionNode.composition_id, CompositionNode.content, Composition.subject_id)
        .join(Composition, Composition.id == CompositionNode.composition_id)
    )).all()
    touched: dict[int, int] = {}
    for row in rows:
        content = row.content
        if not await m.link_images(content, row.subject_id):
            continue
        await m.db.execute(
            update(CompositionNode)
            .where(CompositionNode.id == row.id)
            .values(content=content, updated_at=CompositionNode.updated_at)
        )
        m.report.nodes_updated += 1
        touched[row.composition_id] = row.subject_id
    for composition_id, subject_id in touched.items():
        await media_refs.sync_composition_refs(m.db, composition_id, subject_id)


async def _index_versions(m: _Migrator) -> None:
    rows = (await m.db.execute(
        select(CompositionVersion.id, CompositionVersion.snapshot, Composition.subject_id)
        .join(Composition, Composition.id == CompositionVersion.composition_id)
    )).all()
    for row in rows:
        paths = media_service.collect_legacy_paths(row.snapshot)
        if not paths:
            continue
        legacy_ids = [await m.asset_for(row.subject_id, p) for p in sorted(paths)]
        await media_refs.sync_refs(
            m.db,
            MediaOwnerType.COMPOSITION_VERSION,
            row.id,
            [row.snapshot],
            subject_id=None,
            validate=False,
            extra_asset_ids=[i for i in legacy_ids if i is not None],
        )
        m.report.versions_indexed += 1


async def _map_personal_media(m: _Migrator) -> None:
    for avatar in await m.db.scalars(select(User.avatar_url).where(User.avatar_url.is_not(None))):
        path = media_service.normalize_legacy_path(avatar)
        if path:
            await m._legacy_file(path)
    for images in await m.db.scalars(select(ChatMessage.images).where(ChatMessage.images.is_not(None))):
        for ref in images or []:
            path = media_service.normalize_legacy_path(ref)
            if path:
                await m._legacy_file(path)


async def _store_import_sources(m: _Migrator) -> None:
    tasks = await m.db.scalars(select(ImportTask).where(ImportTask.source_sha256.is_(None)))
    for task in tasks.all():
        source = import_source_file(task.file_path)
        if source is None:
            continue
        sha, _ = await asyncio.to_thread(storage.put_file, source)
        await m.db.execute(
            update(ImportTask)
            .where(ImportTask.id == task.id)
            .values(source_sha256=sha, updated_at=ImportTask.updated_at)
        )
        m.report.import_sources_stored += 1


async def migrate_media(db: AsyncSession, *, apply: bool) -> MigrationReport:
    report = MigrationReport()
    migrator = _Migrator(db, report)
    try:
        await _migrate_questions(migrator)
        await _migrate_stimuli(migrator)
        await _migrate_compositions(migrator)
        await _index_versions(migrator)
        await _map_personal_media(migrator)
        await _store_import_sources(migrator)
        await db.flush()
    except Exception:
        await db.rollback()
        raise
    if apply:
        await db.commit()
    else:
        await db.rollback()
    return report


# --- 清理旧目录 ---------------------------------------------------------------

@dataclass
class PurgeReport:
    media_removed: list[Path] = field(default_factory=list)
    uploads_removed: list[Path] = field(default_factory=list)
    kept_unmapped: list[Path] = field(default_factory=list)

    def lines(self) -> list[str]:
        out = [
            f"可删除的旧媒体文件(已映射到对象存储): {len(self.media_removed)}",
            f"可删除的旧导入源文件(已存入对象存储): {len(self.uploads_removed)}",
            f"未映射而保留的文件: {len(self.kept_unmapped)}",
        ]
        out += [f"  保留 {p}" for p in self.kept_unmapped]
        return out


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _files_under(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file()) if root.is_dir() else []


def _remove_empty_dirs(root: Path) -> None:
    if not root.is_dir():
        return
    for directory in sorted((p for p in root.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            continue


async def purge_legacy_files(db: AsyncSession, *, apply: bool) -> PurgeReport:
    """只删除内容已确认保存在对象存储且被映射/回填的旧文件;其余保留并列出,由人工处理。"""
    report = PurgeReport()
    mapped = {
        row.old_path: row.sha256
        for row in (await db.execute(select(LegacyMediaPath.old_path, LegacyMediaPath.sha256))).all()
    }
    for path in _files_under(settings.MEDIA_DIR):
        key = media_service.LEGACY_MEDIA_PREFIX + path.relative_to(settings.MEDIA_DIR).as_posix()
        sha = mapped.get(key)
        if sha and storage.exists(sha) and _file_sha256(path) == sha:
            report.media_removed.append(path)
        else:
            report.kept_unmapped.append(path)

    stored_sources: dict[Path, str] = {}
    rows = await db.execute(
        select(ImportTask.file_path, ImportTask.source_sha256).where(ImportTask.source_sha256.is_not(None))
    )
    for file_path, sha in rows.all():
        source = import_source_file(file_path)
        if source is not None:
            stored_sources[source] = sha
    for path in _files_under(settings.UPLOAD_DIR):
        sha = stored_sources.get(path.resolve())
        if sha and storage.exists(sha) and _file_sha256(path) == sha:
            report.uploads_removed.append(path)
        else:
            report.kept_unmapped.append(path)

    if apply:
        for path in report.media_removed + report.uploads_removed:
            path.unlink(missing_ok=True)
        _remove_empty_dirs(settings.MEDIA_DIR)
        _remove_empty_dirs(settings.UPLOAD_DIR)
    return report
