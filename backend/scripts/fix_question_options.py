import asyncio
import sys
from pathlib import Path
import json
import argparse

# Add backend directory to path
sys.path.append(str(Path(__file__).parent.parent))

from app.db.session import SessionLocal
from app.models.question import Question
from sqlalchemy import select

async def fix_options(commit: bool = False):
    print(f"Starting fix script... (Commit mode: {commit})")
    async with SessionLocal() as db:
        stmt = select(Question)
        result = await db.execute(stmt)
        questions = result.scalars().all()
        
        print(f"Total questions in DB: {len(questions)}")
        
        count = 0
        fixed_ids = []
        
        for q in questions:
            if q.options and isinstance(q.options, list) and len(q.options) > 0:
                # Check ANY element is string
                has_string = False
                for opt in q.options:
                    if isinstance(opt, str):
                        has_string = True
                        break
                
                if has_string:
                    new_options = []
                    for i, opt in enumerate(q.options):
                        if isinstance(opt, str):
                            parts = opt.split(".", 1)
                            if len(parts) == 2 and len(parts[0]) <= 3:
                                label = parts[0].strip()
                                content = parts[1].strip()
                                new_options.append({"label": label, "content": content})
                            else:
                                label = chr(65 + i) if i < 26 else str(i+1)
                                new_options.append({"label": label, "content": opt})
                        else:
                            new_options.append(opt)
                    
                    # Only update if changed
                    if new_options != q.options:
                        print(f"[Preview] Question {q.id} will be updated.")
                        print(f"  Old: {json.dumps(q.options, ensure_ascii=False)[:100]}...")
                        print(f"  New: {json.dumps(new_options, ensure_ascii=False)[:100]}...")
                        
                        q.options = list(new_options)
                        db.add(q)
                        count += 1
                        fixed_ids.append(q.id)
        
        if count > 0:
            if commit:
                await db.commit()
                print(f"\nSUCCESS: Fixed and committed {count} questions.")
            else:
                await db.rollback()
                print(f"\nDRY RUN: Found {count} questions to fix. No changes were made.")
                print("Run with --commit to apply changes.")
        else:
            print("\nNo questions needed fixing.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fix question options format in database.")
    parser.add_argument("--commit", action="store_true", help="Actually commit changes to the database")
    args = parser.parse_args()
    
    asyncio.run(fix_options(commit=args.commit))
