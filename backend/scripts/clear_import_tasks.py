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

async def clear_import_tasks() -> None:
    print("WARNING: This operation will DELETE ALL IMPORT TASKS from the database.")
    print("Questions associated with these tasks will NOT be deleted, but will be unlinked.")
    print("This action CANNOT be undone.")
    confirm = input("Are you sure you want to proceed? (Type 'yes' to confirm): ")
    
    if confirm != 'yes':
        print("Operation cancelled.")
        return

    async with SessionLocal() as db:
        try:
            logger.info("Starting to clear all import tasks...")
            
            # Unlink questions from import tasks first to avoid foreign key constraints
            logger.info("Unlinking questions from import tasks...")
            await db.execute(text("UPDATE questions SET import_task_id = NULL"))
            
            # Delete import tasks
            logger.info("Deleting from import_tasks...")
            await db.execute(text("DELETE FROM import_tasks"))
            
            await db.commit()
            logger.info("Successfully cleared all import tasks.")
            
        except Exception as e:
            logger.error(f"Error clearing import tasks: {e}")
            await db.rollback()
            raise
        finally:
            # Dispose of the engine to close all connections
            await engine.dispose()

if __name__ == "__main__":
    asyncio.run(clear_import_tasks())
