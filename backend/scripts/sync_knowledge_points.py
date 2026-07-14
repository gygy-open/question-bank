import asyncio
import logging
import sys
from pathlib import Path

# Add backend directory to path
sys.path.append(str(Path(__file__).parent.parent))

from app.db.session import SessionLocal, engine
from app.crud.crud_knowledge_point import knowledge_point
from app.models.knowledge_point import KnowledgePoint
from app.services.embedding import reload_embedding_function
from sqlalchemy import select

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def sync_all_knowledge_points():
    # Initialize embedding function
    await reload_embedding_function()

    logger.info("Starting full sync of knowledge points to ChromaDB...")
    
    async with SessionLocal() as db:
        # Fetch all knowledge points
        result = await db.execute(select(KnowledgePoint))
        kps = result.scalars().all()
        
        total = len(kps)
        logger.info(f"Found {total} knowledge points.")
        
        for i, kp in enumerate(kps):
            try:
                await knowledge_point._sync_to_vector_store(db, kp)
                if (i + 1) % 10 == 0:
                    logger.info(f"Synced {i + 1}/{total}...")
            except Exception as e:
                logger.error(f"Error syncing KP {kp.id}: {e}")
                
    logger.info("Sync completed!")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(sync_all_knowledge_points())
