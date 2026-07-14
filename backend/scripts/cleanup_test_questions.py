import logging
import sys
import os
import asyncio

# Add the parent directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.db.session import SessionLocal
from app.models.question import Question, question_categories, question_tags

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def cleanup(db: AsyncSession) -> None:
    # Find IDs of questions to delete
    stmt = select(Question.id).where(Question.content.like("%(Random ID:%"))
    result = await db.execute(stmt)
    question_ids = result.scalars().all()
    
    if not question_ids:
        logger.info("No test questions found to delete.")
        return

    logger.info(f"Found {len(question_ids)} questions to delete.")

    # Delete from association tables first
    stmt_cats = delete(question_categories).where(question_categories.c.question_id.in_(question_ids))
    await db.execute(stmt_cats)
    
    stmt_tags = delete(question_tags).where(question_tags.c.question_id.in_(question_ids))
    await db.execute(stmt_tags)

    # Delete questions
    stmt_q = delete(Question).where(Question.id.in_(question_ids))
    await db.execute(stmt_q)
    
    await db.commit()
    logger.info("Cleanup complete.")

async def main() -> None:
    async with SessionLocal() as db:
        await cleanup(db)

if __name__ == "__main__":
    asyncio.run(main())
