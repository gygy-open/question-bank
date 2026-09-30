"""内容寻址文件存储:所有持久文件按 sha256 存放,业务代码不自行拼接路径。

布局(均在 settings.DATA_DIR 下):
- storage/objects/ab/cd/<sha256>  不可变原件,无扩展名,类型以数据库 mime 为准
- tmp/jobs/<job_id>/              单次处理的工作目录,结束即删
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Iterator

from app.core.config import settings

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CHUNK = 1024 * 1024
_STALE_JOB_SECONDS = 24 * 3600


class StorageError(Exception):
    pass


def _objects_root() -> Path:
    return settings.STORAGE_DIR / "objects"


def _jobs_root() -> Path:
    return settings.TMP_DIR / "jobs"


def object_path(sha256: str) -> Path:
    if not _SHA256_RE.match(sha256 or ""):
        raise StorageError(f"invalid object key: {sha256!r}")
    return _objects_root() / sha256[:2] / sha256[2:4] / sha256


def exists(sha256: str) -> bool:
    return object_path(sha256).is_file()


def iter_objects() -> Iterator[tuple[str, Path]]:
    root = _objects_root()
    if not root.is_dir():
        return
    for path in root.glob("*/*/*"):
        if path.is_file() and _SHA256_RE.match(path.name):
            yield path.name, path


def _publish(tmp: Path, sha256: str) -> Path:
    target = object_path(sha256)
    if target.is_file():
        tmp.unlink(missing_ok=True)
        # 复用已有对象也刷新 mtime:GC 按 mtime 判定宽限期,避免误删刚被重新引用、尚未提交的对象。
        os.utime(target)
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(tmp, target)
    return target


def _staging_file() -> Path:
    staging = settings.TMP_DIR / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    return staging / uuid.uuid4().hex


def put_bytes(data: bytes) -> str:
    """写入对象并返回 sha256;内容已存在时不重复写。"""
    sha256 = hashlib.sha256(data).hexdigest()
    if exists(sha256):
        return sha256
    tmp = _staging_file()
    tmp.write_bytes(data)
    _publish(tmp, sha256)
    return sha256


def put_stream(stream: BinaryIO) -> tuple[str, int]:
    """边读边算哈希写入对象,返回 (sha256, 字节数)。"""
    digest = hashlib.sha256()
    size = 0
    tmp = _staging_file()
    try:
        with open(tmp, "wb") as out:
            while chunk := stream.read(_CHUNK):
                digest.update(chunk)
                size += len(chunk)
                out.write(chunk)
        sha256 = digest.hexdigest()
        _publish(tmp, sha256)
        return sha256, size
    finally:
        tmp.unlink(missing_ok=True)


def put_file(path: Path) -> tuple[str, int]:
    with open(path, "rb") as stream:
        return put_stream(stream)


def read_bytes(sha256: str) -> bytes:
    path = object_path(sha256)
    if not path.is_file():
        raise StorageError(f"object not found: {sha256}")
    return path.read_bytes()


def delete(sha256: str) -> None:
    object_path(sha256).unlink(missing_ok=True)


@contextmanager
def job_dir() -> Iterator[Path]:
    """单次处理的临时工作目录,退出时连同内容一起删除。"""
    path = _jobs_root() / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def cleanup_stale_tmp(max_age_seconds: int = _STALE_JOB_SECONDS) -> int:
    """清理进程异常退出遗留的工作目录与暂存文件,返回删除的条目数。"""
    removed = 0
    cutoff = time.time() - max_age_seconds
    for root in (_jobs_root(), settings.TMP_DIR / "staging"):
        if not root.is_dir():
            continue
        for entry in root.iterdir():
            try:
                if entry.stat().st_mtime >= cutoff:
                    continue
                if entry.is_dir():
                    shutil.rmtree(entry, ignore_errors=True)
                else:
                    entry.unlink(missing_ok=True)
                removed += 1
            except OSError:
                continue
    return removed
