"""把"外部给出的路径"解析为受控根目录内的真实文件,越界一律拒绝。"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from app.core import storage
from app.core.config import settings

VIRTUAL_SOURCE = "virtual"


def resolve_within(root: Path, candidate: Union[str, Path, None]) -> Optional[Path]:
    """解析 candidate 并确认其位于 root 之内;相对路径按 DATA_DIR 解析(兼容历史记录)。"""
    if not candidate:
        return None
    try:
        path = Path(candidate)
        if not path.is_absolute():
            path = settings.DATA_DIR / path
        resolved = path.resolve()
        root_resolved = root.resolve()
    except (OSError, ValueError):
        return None
    if resolved == root_resolved or not resolved.is_relative_to(root_resolved):
        return None
    return resolved


def import_source_file(file_path: Optional[str]) -> Optional[Path]:
    """导入任务记录的源文件:必须在 UPLOAD_DIR 内且存在。"""
    if not file_path or file_path == VIRTUAL_SOURCE:
        return None
    resolved = resolve_within(settings.UPLOAD_DIR, file_path)
    return resolved if resolved is not None and resolved.is_file() else None


def task_source_file(file_path: Optional[str], source_sha256: Optional[str]) -> Optional[Path]:
    """导入任务的源文件:优先取对象存储,其次是历史 UPLOAD_DIR 路径。"""
    if source_sha256 and storage.exists(source_sha256):
        return storage.object_path(source_sha256)
    return import_source_file(file_path)


def sanitize_client_source_path(file_path: Optional[str]) -> str:
    """客户端回传的源文件路径只在指向 UPLOAD_DIR 内的现存文件时才采信。"""
    resolved = import_source_file(file_path)
    return str(resolved) if resolved is not None else VIRTUAL_SOURCE
