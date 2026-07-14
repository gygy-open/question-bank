import asyncio
import sys
import os
from pathlib import Path
from sqlalchemy import select, func

# Add backend directory to path
# Assuming script is in backend/scripts/ and we want to add backend/ to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal
from app.models.question import Question

async def main():
    async with SessionLocal() as db:
        # Check count of questions with import_task_id = 13
        stmt = select(func.count()).select_from(Question).where(Question.import_task_id == 13)
        result = await db.execute(stmt)
        count = result.scalar_one()
        print(f"Questions with import_task_id=13: {count}")
        
        # Check total questions
        stmt = select(func.count()).select_from(Question)
        result = await db.execute(stmt)
        total = result.scalar_one()
        print(f"Total questions: {total}")
        
        # Check if there are any questions with NULL import_task_id created recently
        stmt = select(Question.id, Question.created_at, Question.import_task_id).order_by(Question.created_at.desc()).limit(5)
        result = await db.execute(stmt)
        print("Recent questions:")
        for row in result:
            print(row)

if __name__ == "__main__":
    asyncio.run(main())
