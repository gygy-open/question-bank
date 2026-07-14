import logging
from typing import List, Dict, Any
from chromadb import EmbeddingFunction, Documents, Embeddings
import openai
import google.genai as genai
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import SessionLocal
from app.crud.crud_system_setting import system_setting
from app.models.ai_config import AIModel
from app.core.vector_store import VectorStore

logger = logging.getLogger(__name__)

class AIProviderEmbeddingFunction(EmbeddingFunction):
    def __init__(self, provider_type: str, api_key: str, base_url: str = None, model_name: str = None):
        self.provider_type = provider_type
        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model_name

    def __call__(self, input: Documents) -> Embeddings:
        if not self.api_key:
            logger.warning("No API key provided for embedding function")
            return [[] for _ in input]

        try:
            if self.provider_type == "openai":
                return self._get_openai_embeddings(input)
            elif self.provider_type == "gemini":
                return self._get_gemini_embeddings(input)
            else:
                logger.error(f"Unknown provider type: {self.provider_type}")
                return [[] for _ in input]
        except Exception as e:
            logger.error(f"Error generating embeddings: {e}")
            return [[] for _ in input]

    def _get_openai_embeddings(self, texts: List[str]) -> Embeddings:
        client = openai.Client(api_key=self.api_key, base_url=self.base_url)
        model = self.model_name or "text-embedding-3-small"
        
        # Replace newlines
        clean_texts = [text.replace("\n", " ") for text in texts]
        
        response = client.embeddings.create(
            input=clean_texts,
            model=model
        )
        return [data.embedding for data in response.data]

    def _get_gemini_embeddings(self, texts: List[str]) -> Embeddings:
        client_kwargs = {"api_key": self.api_key}
        if self.base_url:
            client_kwargs["http_options"] = {"base_url": self.base_url}
            
        client = genai.Client(**client_kwargs)
        model = self.model_name or "text-embedding-004"
        
        embeddings = []
        # Gemini sync client might not support batching in the same way, or it does.
        # Using loop for safety as in the async version, but sync here.
        for text in texts:
            resp = client.models.embed_content(
                model=model,
                contents=text
            )
            embeddings.append(resp.embedding.values)
            
        return embeddings

async def reload_embedding_function():
    """
    Reloads the embedding function from the database configuration.
    This should be called on startup and whenever the AI_EMBEDDING_MODEL_ID setting changes.
    """
    logger.info("Reloading embedding function configuration...")
    async with SessionLocal() as db:
        try:
            # Try to get embedding model setting
            setting = await system_setting.get_by_key(db, "AI_EMBEDDING_MODEL_ID")
            
            if not setting or not setting.value:
                logger.warning("No AI_EMBEDDING_MODEL_ID configured. Vector Store will be unavailable.")
                VectorStore.set_embedding_function(None)
                return

            try:
                model_id = int(setting.value)
                stmt = select(AIModel).options(selectinload(AIModel.provider)).where(AIModel.id == model_id)
                result = await db.execute(stmt)
                model = result.scalar_one_or_none()
                
                if model and model.provider:
                    ef = AIProviderEmbeddingFunction(
                        provider_type=model.provider.interface_type,
                        api_key=model.provider.api_key,
                        base_url=model.provider.base_url,
                        model_name=model.name
                    )
                    VectorStore.set_embedding_function(ef)
                    logger.info(f"Initialized VectorStore with embedding model: {model.name} ({model.provider.name})")
                else:
                    logger.error(f"Embedding model ID {model_id} not found or has no provider. Vector Store unavailable.")
                    VectorStore.set_embedding_function(None)
            except ValueError:
                logger.error(f"Invalid AI_EMBEDDING_MODEL_ID value: {setting.value}")
                VectorStore.set_embedding_function(None)
                
        except Exception as e:
            logger.error(f"Failed to initialize embedding function: {e}")
            VectorStore.set_embedding_function(None)
