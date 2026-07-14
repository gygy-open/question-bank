from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

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

    # File Uploads
    UPLOAD_DIR: Path = Path("uploads")
    MEDIA_DIR: Path = Path("static/media")

    # Database
    DB_URL: str = "mysql+aiomysql://question_bank:question_bank@localhost:3306/question_bank"

    # ChromaDB
    CHROMADB_HOST: str = "localhost"
    CHROMADB_PORT: int = 8001

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

settings = Settings()
