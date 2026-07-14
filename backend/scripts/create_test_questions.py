import logging
import sys
import os
import asyncio
import random

# Add the parent directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import SessionLocal
from app.crud.crud_question import question as crud_question
from app.crud.crud_category import category as crud_category
from app.schemas.question import QuestionCreate
from app.models.question import QuestionType, QuestionStatus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def create_questions(db: AsyncSession) -> None:
    # Get all categories
    categories = await crud_category.get_multi(db, limit=1000)
    if not categories:
        logger.warning("No categories found. Please run import_math_categories.py first or create some categories.")
        # Try to create a dummy category if none exist
        from app.schemas.category import CategoryCreate
        from app.crud.crud_subject import subject as crud_subject
        
        subjects = await crud_subject.get_multi(db)
        if not subjects:
             logger.error("No subjects found. Run initial_data.py first.")
             return
             
        cat_in = CategoryCreate(name="Test Category", subject_id=subjects[0].id, code="TEST001")
        cat = await crud_category.create(db, obj_in=cat_in)
        categories = [cat]
        logger.info("Created test category.")
    
    category_ids = [c.id for c in categories]

    # Sample data
    contents = [
        "已知集合 $A=\\{x|x^2-2x-3<0\\}$，集合 $B=\\{x|y=\\ln(2-x)\\}$，则 $A\\cap B=$ (   )",
        "函数 $f(x)=\\sin(2x+\\frac{\\pi}{3})$ 的最小正周期是 (   )",
        "若复数 $z$ 满足 $z(1+i)=2i$，则 $|z|=$ (   )",
        "已知向量 $\\vec{a}=(1,2)$，$\\vec{b}=(x,1)$，若 $\\vec{a}//\\vec{b}$，则 $x=$ (   )",
        "在 $\\triangle ABC$ 中，角 $A,B,C$ 的对边分别为 $a,b,c$，若 $a=2, b=2\\sqrt{2}, A=\\frac{\\pi}{4}$，则 $B=$ (   )",
        "求函数 $f(x) = x^3 - 3x + 1$ 的极值。",
        "解不等式 $\\frac{2x-1}{x+1} \\ge 1$。",
        "已知数列 $\\{a_n\\}$ 满足 $a_1=1, a_{n+1}=2a_n+1$，求通项公式。",
        "计算定积分 $\\int_0^1 (x^2+1)dx$。",
        "求过点 $(1,2)$ 且与直线 $2x-y+1=0$ 平行的直线方程。"
    ]
    
    analyses = [
        "本题考查集合的运算，属于基础题。",
        "利用三角函数的周期公式 $T=\\frac{2\\pi}{\\omega}$ 求解。",
        "利用复数的除法运算求出 $z$，再求模。",
        "利用向量共线的坐标表示求解。",
        "利用正弦定理求解。",
        "求导，令导数为0，判断单调性。",
        "移项通分，利用穿针引线法求解。",
        "构造等比数列求解。",
        "利用微积分基本定理求解。",
        "利用点斜式或斜截式求解。"
    ]

    for i in range(20):
        q_type = random.choice(list(QuestionType))
        content = random.choice(contents)
        
        options = None
        if q_type in [QuestionType.SINGLE_CHOICE, QuestionType.MULTIPLE_CHOICE]:
            options = [
                {"label": "A", "text": f"Option A for {i}"},
                {"label": "B", "text": f"Option B for {i}"},
                {"label": "C", "text": f"Option C for {i}"},
                {"label": "D", "text": f"Option D for {i}"},
            ]
            answer = random.choice(["A", "B", "C", "D"])
        elif q_type == QuestionType.TRUE_FALSE:
            answer = random.choice(["正确", "错误"])
        else:
            answer = "这是参考答案..."

        question_in = QuestionCreate(
            content=content,
            q_type=q_type,
            difficulty=random.randint(1, 5),
            options=options,
            answer=answer,
            analysis=random.choice(analyses),
            category_ids=[random.choice(category_ids)],
            status=QuestionStatus.PUBLISHED
        )
        
        await crud_question.create_with_tags(db, obj_in=question_in)
        logger.info(f"Created question: {content[:20]}...")

async def main() -> None:
    async with SessionLocal() as db:
        await create_questions(db)

if __name__ == "__main__":
    asyncio.run(main())
