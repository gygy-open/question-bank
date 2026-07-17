import json
import os
import sys
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_data_dir() -> Path:
    """Directory for runtime-writable data (config.json, sqlite db, uploads).

    - Frozen (PyInstaller desktop build): OS per-user data directory.
    - Development / server: the ``backend/`` project directory.
    """
    if getattr(sys, "frozen", False):
        if sys.platform == "win32":
            base = Path(os.getenv("APPDATA", str(Path.home())))
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support"
        else:
            base = Path(os.getenv("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
        return base / "QuestionBank"
    # config.py -> app/core/config.py, parents[2] == backend/
    return Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    PROJECT_NAME: str = "Question Bank API"
    API_V1_STR: str = "/api/v1"

    LOG_LEVEL: str = "INFO"

    # Security
    # Must be overridden via SECRET_KEY env var in any non-dev deployment.
    # Generate with: openssl rand -hex 32
    SECRET_KEY: str = "insecure-dev-only-CHANGE-ME"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8 # 8 days

    # Runtime-writable data directory (sqlite db, config.json, uploads).
    DATA_DIR: Path = _default_data_dir()

    # File Uploads. Relative values are resolved under DATA_DIR (see validator),
    # so a packaged desktop build writes to the per-user data directory instead
    # of next to the (read-only) executable.
    UPLOAD_DIR: Path = Path("uploads")
    MEDIA_DIR: Path = Path("static/media")

    # Database. Empty by default: when neither an env/.env value nor a runtime
    # config.json is present, the app boots into first-run "setup mode".
    DB_URL: str = ""

    # ChromaDB
    CHROMADB_HOST: str = "localhost"
    CHROMADB_PORT: int = 8001
    # "" = auto: embedded (PersistentClient) when frozen/desktop, http otherwise.
    # Explicit values: "embedded" | "http".
    CHROMADB_MODE: str = ""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

    @model_validator(mode="after")
    def _resolve_data_paths(self) -> "Settings":
        # Anchor relative upload/media paths to the writable data directory.
        if not self.UPLOAD_DIR.is_absolute():
            self.UPLOAD_DIR = self.DATA_DIR / self.UPLOAD_DIR
        if not self.MEDIA_DIR.is_absolute():
            self.MEDIA_DIR = self.DATA_DIR / self.MEDIA_DIR
        return self

    @property
    def STATIC_DIR(self) -> Path:
        """Root directory served at ``/static`` (contains ``media/``)."""
        return self.DATA_DIR / "static"

settings = Settings()


# ---------------------------------------------------------------------------
# Runtime (first-run) configuration — stored in a writable JSON file.
#
# Database connection settings are bootstrap-level and therefore CANNOT live in
# the database itself. They are resolved with the following precedence:
#   1. Explicit DB_URL from environment / .env  (docker & server deployments)
#   2. runtime config.json written by the setup wizard  (desktop / intranet)
#   3. None  -> the app starts in setup mode
# ---------------------------------------------------------------------------

def runtime_config_path() -> Path:
    return settings.DATA_DIR / "config.json"


def load_runtime_config() -> dict:
    path = runtime_config_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_runtime_config(data: dict) -> None:
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = runtime_config_path()
    merged = load_runtime_config()
    merged.update(data)
    path.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")


def get_db_url() -> str:
    """Resolve the active database URL, or an empty string if not configured."""
    if settings.DB_URL:
        return settings.DB_URL
    return load_runtime_config().get("db_url", "") or ""


def default_sqlite_url() -> str:
    """Zero-config SQLite URL under the writable data directory."""
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    db_path = (settings.DATA_DIR / "app.db").as_posix()
    return f"sqlite+aiosqlite:///{db_path}"


def is_configured() -> bool:
    return bool(get_db_url())


def chroma_mode() -> str:
    """Resolve the ChromaDB mode: 'embedded' or 'http'.

    Precedence: explicit CHROMADB_MODE (env/.env) > runtime config.json >
    auto (embedded for a frozen desktop build, http for server/docker).
    """
    mode = settings.CHROMADB_MODE or load_runtime_config().get("chroma_mode", "")
    if mode:
        return mode
    return "embedded" if getattr(sys, "frozen", False) else "http"


def chroma_path() -> Path:
    """Filesystem location for the embedded (PersistentClient) ChromaDB store."""
    return settings.DATA_DIR / "chroma"
