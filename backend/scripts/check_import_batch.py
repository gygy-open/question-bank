import asyncio
import sys
import os

# Add backend directory to python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.db.session import SessionLocal
from sqlalchemy import select
from app.models.subject import Subject

async def main():
    async with SessionLocal() as db:
        subjects = (await db.execute(select(Subject))).scalars().all()
        for s in subjects:
            print(f"Subject: {s.id} - {s.name}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
