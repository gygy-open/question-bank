from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

connect_args = {}
# if settings.DB_URL.startswith("sqlite"):
#     connect_args = {"check_same_thread": False}

engine = create_async_engine(
    settings.DB_URL,
    echo=False,
    future=True,
    # connect_args=connect_args
)
SessionLocal = sessionmaker(
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False
)
