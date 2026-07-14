import logging
import sys
import os
import asyncio
import pandas as pd
from slugify import slugify

# Add the parent directory to sys.path to allow importing app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select, delete, update
from app.db.session import SessionLocal, engine
from app.models.subject import Subject
from app.models.knowledge_point import KnowledgePoint
from app.crud.crud_knowledge_point import knowledge_point as crud_knowledge_point
from app.schemas.knowledge_point import KnowledgePointCreate
from app.services.embedding import reload_embedding_function
from app.core.vector_store import VectorStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def clear_knowledge_points(db: AsyncSession, subject_id: int):
    logger.info(f"Clearing knowledge points for subject {subject_id}...")
    try:
        is_sqlite = db.bind.dialect.name == 'sqlite'
        
        if is_sqlite:
            # Disable FK check for SQLite to allow mass deletion of self-referential table
            await db.execute(text("PRAGMA foreign_keys = OFF"))
        else:
            # For Postgres/MySQL, break self-references first by setting parent_id to NULL
            await db.execute(
                update(KnowledgePoint)
                .where(KnowledgePoint.subject_id == subject_id)
                .values(parent_id=None)
            )
            await db.flush() # Ensure update is processed before delete

        await db.execute(
            delete(KnowledgePoint).where(KnowledgePoint.subject_id == subject_id)
        )
        await db.commit()
        logger.info("Knowledge points cleared.")
    except Exception as e:
        logger.error(f"Failed to clear knowledge points: {e}")
        await db.rollback()
    finally:
        if db.bind.dialect.name == 'sqlite':
            await db.execute(text("PRAGMA foreign_keys = ON"))

async def get_or_create_knowledge_point(db: AsyncSession, name: str, subject_id: int, parent_id: int = None) -> KnowledgePoint:
    # Check if exists in DB (to avoid duplicates in this run or previous runs)
    result = await db.execute(select(KnowledgePoint).filter(
        KnowledgePoint.subject_id == subject_id,
        KnowledgePoint.parent_id == parent_id,
        KnowledgePoint.name == name
    ))
    existing = result.scalars().first()
    
    kp = None
    if existing:
        kp = existing
    else:
        # Generate unique slug
        base_slug = slugify(name)
        if not base_slug: # Fallback for non-latin characters if slugify fails or returns empty (though python-slugify handles chinese)
            base_slug = "kp" 
        
        slug = base_slug
        counter = 1
        while True:
            # Check global uniqueness for subject
            result = await db.execute(select(KnowledgePoint).filter(
                KnowledgePoint.subject_id == subject_id,
                KnowledgePoint.slug == slug
            ))
            slug_exists = result.scalars().first()
            if not slug_exists:
                break
            slug = f"{base_slug}-{counter}"
            counter += 1
        
        db_obj = KnowledgePoint(
            name=name,
            slug=slug,
            subject_id=subject_id,
            parent_id=parent_id
        )
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        logger.info(f"Created knowledge point: {name} (slug: {slug}, parent: {parent_id})")
        kp = db_obj

        # Sync to Vector Store (Only for new items)
        try:
            # Use asyncio.to_thread to avoid blocking the event loop with network I/O
            await asyncio.to_thread(
                VectorStore.upsert_knowledge_point,
                id=kp.id,
                text=kp.name,
                metadata={"subject_id": kp.subject_id, "slug": kp.slug}
            )
            logger.info(f"Synced knowledge point to vector store: {kp.name}")
        except Exception as e:
            logger.error(f"Failed to sync to vector store: {e}")

    return kp

async def import_knowledge_points(db: AsyncSession, file_path: str):
    # 1. Get Math Subject
    result = await db.execute(select(Subject).filter(Subject.slug == "math"))
    subject = result.scalars().first()
    if not subject:
        logger.error("Subject 'math' not found. Please run initial_data.py first.")
        return
    
    logger.info(f"Importing into Subject: {subject.name}")

    # Clear existing knowledge points
    # await clear_knowledge_points(db, subject.id)

    # 2. Read Excel
    df = pd.read_excel(file_path)
    
    # 3. Iterate rows
    # Columns: '一级目录', '二级目录', '三级目录', '四级目录', '五级目录'
    
    for index, row in df.iterrows():
        # Build path dynamically filtering out empty levels
        # This handles cases where intermediate levels (like level 4) are empty but deeper levels (like level 5) exist.
        # The deeper level effectively "moves up" to fill the gap.
        raw_path = [row['一级目录'], row['二级目录'], row['三级目录'], row['四级目录'], row['五级目录']]
        path = []
        for p in raw_path:
            if pd.isna(p):
                continue
            s = str(p).strip()
            if s == "":
                continue
            path.append(s)
        
        if not path:
            continue
            
        current_parent_id = None
        for name in path:
            kp = await get_or_create_knowledge_point(db, name, subject.id, current_parent_id)
            current_parent_id = kp.id

async def main():
    # Initialize embedding function
    await reload_embedding_function()

    file_path = os.path.join(os.path.dirname(__file__), "高考所有知识点.xlsx")
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return

    async with SessionLocal() as db:
        try:
            await import_knowledge_points(db, file_path)
        except Exception as e:
            logger.error(f"An error occurred: {e}")
            import traceback
            traceback.print_exc()
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
