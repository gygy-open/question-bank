"""Seed a small set of math knowledge points for local development/testing.

Usage:
    uv run python scripts/seed_knowledge_points.py
"""
import logging
import sys
import os
import asyncio

# Add the parent directory to sys.path to allow importing app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slugify import slugify
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import SessionLocal, engine
from app.models.subject import Subject
from app.models.knowledge_point import KnowledgePoint
from app.crud.crud_knowledge_point import knowledge_point as crud_knowledge_point
from app.schemas.knowledge_point import KnowledgePointCreate

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 简单的数学知识点树, 可按需扩充
MATH_KNOWLEDGE_TREE = {
    "代数": {
        "方程与不等式": ["一元一次方程", "一元二次方程", "一元一次不等式"],
        "函数": ["一次函数", "二次函数", "反比例函数"],
    },
    "几何": {
        "平面几何": ["三角形", "四边形", "圆"],
        "立体几何": ["空间几何体", "空间向量"],
    },
    "概率与统计": {
        "概率": ["古典概型", "条件概率"],
        "统计": ["数据的收集与整理", "统计图表"],
    },
}


async def get_or_create_knowledge_point(
    db: AsyncSession, name: str, subject_id: int, parent_id: int | None = None
) -> KnowledgePoint:
    result = await db.execute(
        select(KnowledgePoint).filter(
            KnowledgePoint.subject_id == subject_id,
            KnowledgePoint.parent_id == parent_id,
            KnowledgePoint.name == name,
        )
    )
    existing = result.scalars().first()
    if existing:
        return existing

    base_slug = slugify(name) or "kp"
    slug = base_slug
    counter = 1
    while True:
        result = await db.execute(
            select(KnowledgePoint).filter(
                KnowledgePoint.subject_id == subject_id,
                KnowledgePoint.slug == slug,
            )
        )
        if not result.scalars().first():
            break
        slug = f"{base_slug}-{counter}"
        counter += 1

    kp_in = KnowledgePointCreate(
        name=name, slug=slug, subject_id=subject_id, parent_id=parent_id
    )
    kp = await crud_knowledge_point.create(db, obj_in=kp_in)
    logger.info(f"Created knowledge point: {name} (slug: {slug}, parent: {parent_id})")
    return kp


async def seed_knowledge_points(db: AsyncSession):
    result = await db.execute(select(Subject).filter(Subject.slug == "math"))
    subject = result.scalars().first()
    if not subject:
        logger.error("Subject 'math' not found. Please create it first (via onboarding or the subjects page).")
        return

    logger.info(f"Seeding knowledge points into subject: {subject.name}")

    for level1_name, level2_dict in MATH_KNOWLEDGE_TREE.items():
        level1 = await get_or_create_knowledge_point(db, level1_name, subject.id)
        for level2_name, level3_names in level2_dict.items():
            level2 = await get_or_create_knowledge_point(
                db, level2_name, subject.id, level1.id
            )
            for level3_name in level3_names:
                await get_or_create_knowledge_point(
                    db, level3_name, subject.id, level2.id
                )

    logger.info("Done seeding knowledge points.")


async def main():
    async with SessionLocal() as db:
        try:
            await seed_knowledge_points(db)
        except Exception as e:
            logger.error(f"An error occurred: {e}")
            import traceback

            traceback.print_exc()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
