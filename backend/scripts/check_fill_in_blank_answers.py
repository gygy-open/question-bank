"""检查填空题的答案格式"""

import asyncio
from sqlalchemy import text
from app.db.session import SessionLocal
import json

async def check_fill_in_blank_answers():
    """检查数据库中填空题的答案格式"""
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
        
        invalid_count = 0
        for row in rows:
            qid = row[0]
            content = row[1][:50] + "..." if len(row[1]) > 50 else row[1]
            answer = row[2]
            
            # 检查 answer 是否为有效 JSON
            is_valid = False
            if answer is None:
                status = "NULL"
            else:
                try:
                    parsed = json.loads(answer)
                    if isinstance(parsed, list):
                        status = f"✓ JSON (length: {len(parsed)})"
                        is_valid = True
                    else:
                        status = "✗ JSON but not a list"
                except json.JSONDecodeError:
                    status = f"✗ Invalid JSON: {answer[:50]}"
            
            if not is_valid:
                invalid_count += 1
                print(f"ID {qid}: {status}")
                print(f"  Content: {content}")
                print(f"  Answer: {answer}")
                print()
        
        print(f"\n总结：")
        print(f"  总计: {len(rows)} 条")
        print(f"  无效: {invalid_count} 条")
        print(f"  有效: {len(rows) - invalid_count} 条")

if __name__ == "__main__":
    asyncio.run(check_fill_in_blank_answers())
