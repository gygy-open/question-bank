import sys
import logging
from pathlib import Path
from contextlib import asynccontextmanager
# Add the project root directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.api.v1.api import api_router
from app.core.config import settings
from app.services.embedding import reload_embedding_function

logging.basicConfig(level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Embedding Function
    await reload_embedding_function()
    
    yield
    # Shutdown

app = FastAPI(title="Question Bank API", lifespan=lifespan)

# Ensure static directories exist
settings.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

app.include_router(api_router, prefix="/api/v1")

@app.get("/")
def read_root():
    return {"message": "Welcome to Question Bank API"}
