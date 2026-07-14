import asyncio
import sys
from pathlib import Path

# Add backend directory to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal
from app.crud.crud_question import question as crud_question

async def main():
    async with SessionLocal() as db:
        print("Testing get_multi_with_filters with import_task_id=13")
        results = await crud_question.get_multi_with_filters(db, import_task_id=13)
        print(f"Results count: {len(results)}")
        for q in results:
            print(f"ID: {q.id}, Content: {q.content[:20]}..., TaskID: {q.import_task_id}")

if __name__ == "__main__":
    asyncio.run(main())
