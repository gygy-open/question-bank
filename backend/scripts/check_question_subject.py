import asyncio
import sys
from pathlib import Path
from sqlalchemy import select

# Add backend directory to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal
from app.models.question import Question

async def main():
    async with SessionLocal() as db:
        stmt = select(Question.id, Question.subject_id).where(Question.import_task_id == 13)
        result = await db.execute(stmt)
        for row in result:
            print(f"Question ID: {row.id}, Subject ID: {row.subject_id}")

if __name__ == "__main__":
    asyncio.run(main())
