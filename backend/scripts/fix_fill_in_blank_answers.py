"""修复填空题的答案格式"""

import asyncio
from sqlalchemy import text
from app.db.session import SessionLocal
import json

async def fix_fill_in_blank_answers():
    """将填空题的答案转换为 JSON 格式"""
    async with SessionLocal() as session:
        # 查询所有填空题
        result = await session.execute(
            text("SELECT id, content, answer FROM questions WHERE q_type = 'FILL_IN_THE_BLANK'")
        )
        rows = result.fetchall()
        
        if not rows:
            print("没有找到填空题")
            return
        
        print(f"\n=== 找到 {len(rows)} 条填空题 ===\n")
        
        fixed_count = 0
        for row in rows:
            qid = row[0]
            content = row[1][:50] + "..." if len(row[1]) > 50 else row[1]
            answer = row[2]
            
            # 检查是否需要修复
            needs_fix = False
            if answer is None:
                print(f"ID {qid}: 答案为 NULL，跳过")
                continue
            
            try:
                parsed = json.loads(answer)
                if isinstance(parsed, list):
                    print(f"ID {qid}: 已经是有效的 JSON 列表，跳过")
                    continue
                else:
                    needs_fix = True
                    print(f"ID {qid}: JSON 但不是列表，需要转换")
            except json.JSONDecodeError:
                needs_fix = True
                print(f"ID {qid}: 不是有效的 JSON，需要转换")
            
            if needs_fix:
                # 将答案转换为 JSON 列表格式
                # 对于填空题，假设答案可能有多个空，每个空可以有多个可能的答案
                # 简单处理：包装成 [[answer]]
                new_answer = json.dumps([[answer]])
                
                print(f"  原答案: {answer}")
                print(f"  新答案: {new_answer}")
                
                await session.execute(
                    text("UPDATE questions SET answer = :new_answer WHERE id = :qid"),
                    {"new_answer": new_answer, "qid": qid}
                )
                fixed_count += 1
        
        await session.commit()
        
        print(f"\n✓ 已修复 {fixed_count} 条记录")

if __name__ == "__main__":
    asyncio.run(fix_fill_in_blank_answers())
