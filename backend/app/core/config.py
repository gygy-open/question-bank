import json
import os
import secrets
import sys
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Sentinel: any value other than this means SECRET_KEY was supplied explicitly
# (env / .env / docker) and must be respected. When left at the default we fall
# back to a random key persisted in config.json (see validator below).
_INSECURE_DEFAULT_SECRET = "insecure-dev-only-CHANGE-ME"


def _load_or_create_secret_key(data_dir: Path) -> str:
    """Return a stable random secret key, persisted in ``config.json``.

    Used when no SECRET_KEY was provided via env/.env so that tokens survive
    restarts and a packaged desktop build is never left on the insecure default.
    """
    path = data_dir / "config.json"
    data: dict = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    key = data.get("secret_key")
    if not key:
        key = secrets.token_hex(32)
        data["secret_key"] = key
        try:
            data_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except OSError:
            pass
    return key


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
    # If left at the default, a random key is generated and persisted in
    # config.json (see validator). Override via SECRET_KEY env for docker/server.
    SECRET_KEY: str = _INSECURE_DEFAULT_SECRET
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

    # ``extra="ignore"``: a packaged desktop build may run in a directory that
    # happens to contain an unrelated ``.env`` (or the host may export unrelated
    # env vars). Ignore unknown keys instead of crashing on startup.
    model_config = SettingsConfigDict(
        env_file=".env", case_sensitive=True, extra="ignore"
    )

    @model_validator(mode="after")
    def _resolve_data_paths(self) -> "Settings":
        # Anchor relative upload/media paths to the writable data directory.
        if not self.UPLOAD_DIR.is_absolute():
            self.UPLOAD_DIR = self.DATA_DIR / self.UPLOAD_DIR
        if not self.MEDIA_DIR.is_absolute():
            self.MEDIA_DIR = self.DATA_DIR / self.MEDIA_DIR
        # No explicit secret provided -> use a stable random key from config.json.
        if self.SECRET_KEY == _INSECURE_DEFAULT_SECRET:
            self.SECRET_KEY = _load_or_create_secret_key(self.DATA_DIR)
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


def get_lan_share() -> bool:
    """Whether the tray app should bind 0.0.0.0 to share on the local network."""
    return bool(load_runtime_config().get("lan_share", False))


def set_lan_share(enabled: bool) -> None:
    save_runtime_config({"lan_share": bool(enabled)})
