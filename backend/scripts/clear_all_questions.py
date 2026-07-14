import logging
import sys
import os
import asyncio

# Add the parent directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.db.session import SessionLocal, engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def clear_all_questions() -> None:
    print("WARNING: This operation will DELETE ALL QUESTIONS and related data from the database.")
    print("This action CANNOT be undone.")
    confirm = input("Are you sure you want to proceed? (Type 'yes' to confirm): ")
    
    if confirm != 'yes':
        print("Operation cancelled.")
        return

    async with SessionLocal() as db:
        try:
            logger.info("Starting to clear all questions...")
            
            # Delete from association tables first
            logger.info("Deleting from question_tags...")
            await db.execute(text("DELETE FROM question_tags"))
            
            logger.info("Deleting from question_knowledge_points...")
            await db.execute(text("DELETE FROM question_knowledge_points"))
            
            # Delete questions
            logger.info("Deleting from questions...")
            await db.execute(text("DELETE FROM questions"))
            
            await db.commit()
            logger.info("Successfully cleared all questions and associations.")
            
        except Exception as e:
            logger.error(f"Error clearing questions: {e}")
            await db.rollback()
            raise
        finally:
            # Dispose of the engine to close all connections
            await engine.dispose()

if __name__ == "__main__":
    asyncio.run(clear_all_questions())
