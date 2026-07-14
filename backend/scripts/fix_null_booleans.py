import asyncio
import logging
import sys
from sqlalchemy import text

# Add backend directory to path
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.db.session import async_session_maker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def fix_null_booleans():
    async with async_session_maker() as session:
        logger.info("Updating NULL boolean fields to FALSE...")
        
        # Update is_embedding_model
        await session.execute(text("UPDATE ai_models SET is_embedding_model = 0 WHERE is_embedding_model IS NULL"))
        
        # Update is_vision_capable
        await session.execute(text("UPDATE ai_models SET is_vision_capable = 0 WHERE is_vision_capable IS NULL"))
        
        await session.commit()
        logger.info("Done.")

if __name__ == "__main__":
    asyncio.run(fix_null_booleans())
