import asyncio
import json
import logging
import sys
import os
from openai import AsyncOpenAI

# Add backend directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, text, update
from app.db.session import SessionLocal, engine
from app.models.question import Question

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def fix_questions_direct():
    # Initialize OpenAI client
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        logger.error("DASHSCOPE_API_KEY environment variable is not set. Please set it before running.")
        return

    client = AsyncOpenAI(
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )

    async with SessionLocal() as db:
        try:
            # Query questions where options is NULL
            stmt = select(Question.id, Question.content, Question.answer).where(
                text("JSON_TYPE(options) = 'NULL'")
            ).limit(1000).offset(10)
            
            result = await db.execute(stmt)
            questions = result.all()
            
            logger.info(f"Found {len(questions)} questions to process")
            
            for i, q in enumerate(questions):
                logger.info(f"[{i+1}/{len(questions)}] Processing Question ID: {q.id}")
                
                prompt = f"""你是一个专业的数学题目分类助手。请分析以下题目，判断其正确的题目类型，并格式化答案。

题目内容：
{q.content}

原答案：
{q.answer}

请返回一个 JSON 对象，包含以下字段：
1. "id": {q.id} (保持不变)
2. "q_type": 题目类型，必须是以下之一：
   - "fill_in_the_blank" (填空题：题干中有下划线、括号等填空符)
   - "free_response" (解答题：需要计算、证明、作图等)
   - "single_choice" (单选题：虽然现在没有选项，但如果题干明显包含选项内容，请标记为此类)
3. "answer": 格式化后的答案
   - 如果是 "fill_in_the_blank"，必须转换为二维数组格式 `[["答案1a", "答案1b"], ["答案2"]]`。
     * 外层列表对应题目中的每一个空（按顺序）。
     * 内层列表对应每一个空的备选答案（例如 "1/2" 和 "0.5" 均可）。
     * 如果原答案包含 "；" 或 "或"，请将其拆分为该空的备选答案。
     * **LaTeX 格式**：如果答案包含数学公式，**必须**使用 LaTeX 格式并用 `$` 包裹。
   - 如果是 "free_response"，保持原样或优化格式。
   - 如果是 "single_choice"，提取正确选项字母。

仅返回 JSON，不要包含 Markdown 格式标记。
"""

                try:
                    completion = await client.chat.completions.create(
                        model="qwen-plus",
                        messages=[
                            {"role": "system", "content": "你是一个辅助修正数据库数据的专家。"},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.1
                    )
                    
                    content = completion.choices[0].message.content
                    
                    # Clean up markdown code blocks
                    if content.startswith("```json"):
                        content = content[7:]
                    elif content.startswith("```"):
                        content = content[3:]
                    if content.endswith("```"):
                        content = content[:-3]
                    
                    ai_result = json.loads(content.strip())

                    logger.info(f"AI Result for Question ID {q.id}: {ai_result}")
                    
                    new_q_type = ai_result.get("q_type")
                    new_answer = ai_result.get("answer")
                    
                    if not new_q_type:
                        logger.warning(f"Missing q_type for ID {q.id}")
                        continue
                    
                    # Ensure fill-in-the-blank answers are JSON strings
                    if new_q_type == "fill_in_the_blank" and new_answer is not None:
                        if isinstance(new_answer, (list, dict)):
                            new_answer = json.dumps(new_answer, ensure_ascii=False)
                        elif isinstance(new_answer, str):
                            # Verify it's valid JSON
                            try:
                                json.loads(new_answer)
                            except json.JSONDecodeError:
                                # Not valid JSON, wrap it
                                new_answer = json.dumps([[new_answer]], ensure_ascii=False)

                    # Update database
                    stmt_update = (
                        update(Question)
                        .where(Question.id == q.id)
                        .values(
                            q_type=new_q_type,
                            answer=new_answer
                        )
                    )
                    await db.execute(stmt_update)
                    await db.commit()
                    logger.info(f"Updated Question ID: {q.id} -> {new_q_type}")
                    
                except Exception as e:
                    logger.error(f"Error processing ID {q.id}: {e}")
                    # Continue to next question even if one fails

        finally:
            await engine.dispose()

if __name__ == "__main__":
    asyncio.run(fix_questions_direct())
