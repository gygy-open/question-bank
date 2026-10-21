"""发布通道:带预发布后缀(如 1.5.0-alpha.1)的打包桌面版是"测试版",与正式版完全隔离。

隔离项:数据目录、单实例锁、默认端口、托盘名称、局域网主机名。安装包侧的隔离见
deploy/windows/installer.iss 的 Preview 开关。

本模块在 app.core.config 之前被使用(config 导入时就会在数据目录写 config.json),
所以不能导入 config,也不能导入任何会间接导入它的模块。
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Literal, Optional

from app._version import __version__

STABLE_DIR_NAME = "QuestionBank"
PREVIEW_DIR_NAME = "QuestionBank-Preview"
_DECLINED_MARKER = ".seed-declined"
# 不复制:数据库另走 SQLite 在线备份;config.json 最后改写后再写(中途失败也不会指向正式版库);日志与临时文件无需带过去。
_SKIP = {
    "app.db", "app.db-wal", "app.db-shm", "app.db-journal", "config.json", "logs", "tmp", _DECLINED_MARKER,
}


def is_preview(version: str = __version__, frozen: Optional[bool] = None) -> bool:
    if frozen is None:
        frozen = bool(getattr(sys, "frozen", False))
    return frozen and "-" in version


PREVIEW = is_preview()
DEFAULT_PORT = 8001 if PREVIEW else 8000
INSTANCE_MUTEX = "Global\\QuestionBankTrayPreview" if PREVIEW else "Global\\QuestionBankTray"
DISPLAY_NAME = "QuestionBank 测试版" if PREVIEW else "QuestionBank"
MDNS_HOST = "questionbank-preview" if PREVIEW else "questionbank"


def desktop_data_root() -> Path:
    if sys.platform == "win32":
        return Path(os.getenv("APPDATA", str(Path.home())))
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    return Path(os.getenv("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))


def desktop_data_dir(preview: bool = PREVIEW) -> Path:
    return desktop_data_root() / (PREVIEW_DIR_NAME if preview else STABLE_DIR_NAME)


SeedState = Literal["not_needed", "available", "mysql"]


def seed_state(stable: Path, preview: Path) -> SeedState:
    """测试版首次启动时,能否从正式版复制一份数据。"""
    if (preview / "config.json").exists() or (preview / _DECLINED_MARKER).exists():
        return "not_needed"
    config = _read_json(stable / "config.json")
    if not config.get("db_url"):
        return "not_needed"
    return "available" if config.get("db_type", "sqlite") == "sqlite" else "mysql"


def decline_seed(preview: Path) -> None:
    preview.mkdir(parents=True, exist_ok=True)
    (preview / _DECLINED_MARKER).write_text("", encoding="utf-8")


def seed_from_stable(stable: Path, preview: Path) -> None:
    """把正式版数据复制到测试版目录;正式版只读不改,运行中复制也一致。"""
    config = _read_json(stable / "config.json")
    source_db = _sqlite_path(config.get("db_url", "")) or stable / "app.db"
    preview.mkdir(parents=True, exist_ok=True)
    shutil.copytree(stable, preview, ignore=lambda _d, names: [n for n in names if n in _SKIP], dirs_exist_ok=True)

    target_db = preview / "app.db"
    if source_db.exists():
        src = sqlite3.connect(f"file:{source_db.as_posix()}?mode=ro", uri=True)
        try:
            dst = sqlite3.connect(target_db)
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()

    # 复制来的路径仍指向正式版数据库,必须改写,否则测试版会把正式版数据升级掉。
    config["db_url"] = f"sqlite+aiosqlite:///{target_db.as_posix()}"
    config["lan_share"] = False
    (preview / "config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _sqlite_path(db_url: str) -> Optional[Path]:
    prefix = "sqlite+aiosqlite:///"
    return Path(db_url[len(prefix):]) if db_url.startswith(prefix) else None
