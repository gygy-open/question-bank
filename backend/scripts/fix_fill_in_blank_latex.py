import asyncio
import logging
import sys
import os
import json
import re
import argparse

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.question import Question, QuestionType

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Regex for math content (excluding Chinese)
# Allow: numbers, letters, operators, brackets, punctuation commonly used in math, latex commands (\), superscripts, subscripts
MATH_PATTERN = re.compile(r'^[0-9a-zA-Z\+\-\*\/\=\(\)\.\,\s\^\\_\{\}\|<>%]+$')

# Regex for pure numbers (integer or float, positive or negative)
# These do not strictly need LaTeX wrapping
NUMBER_PATTERN = re.compile(r'^-?\d+(\.\d+)?$')

def needs_latex(text: str) -> bool:
    if not text:
        return False
    text = text.strip()
    # Already latex
    if text.startswith('$') and text.endswith('$'):
        return False
    # Contains Chinese -> skip for safety (or handle separately if needed)
    if any('\u4e00' <= char <= '\u9fff' for char in text):
        return False
    # Check if it looks like math
    if MATH_PATTERN.match(text):
        # If it is just a pure number, skip
        if NUMBER_PATTERN.match(text):
            return False
        return True
    return False

def fix_text(text: str) -> str:
    text = text.strip()
    return f"${text}$"

async def main(apply: bool):
    # Configure logging to file
    file_handler = logging.FileHandler("fix_latex_dry_run.log", mode='w', encoding='utf-8')
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)

    logger.info(f"Starting fix script... Mode: {'APPLY' if apply else 'DRY RUN'}")
    
    async with SessionLocal() as db:
        stmt = select(Question).where(Question.q_type == QuestionType.FILL_IN_THE_BLANK)
        result = await db.execute(stmt)
        questions = result.scalars().all()
        
        logger.info(f"Found {len(questions)} fill-in-the-blank questions.")
        
        updated_count = 0
        
        for q in questions:
            if not q.answer:
                continue
                
            try:
                # answer should be a JSON string representing List[List[str]]
                # e.g. '[["1", "2"], ["3"]]'
                answer_data = json.loads(q.answer)
            except json.JSONDecodeError:
                logger.warning(f"Question {q.id}: Invalid JSON answer: {q.answer}")
                continue
                
            if not isinstance(answer_data, list):
                logger.warning(f"Question {q.id}: Answer is not a list: {q.answer}")
                continue

            changed = False
            new_answer_data = []
            
            for blank_idx, blank_options in enumerate(answer_data):
                new_blank_options = []
                
                # Handle case where structure might be wrong (e.g. flat list)
                # The spec says List[List[str]], but let's be robust
                current_options = blank_options
                if not isinstance(blank_options, list):
                    if isinstance(blank_options, str):
                        current_options = [blank_options]
                    else:
                        # Unknown type, keep as is
                        new_answer_data.append(blank_options)
                        continue

                blank_changed = False
                for opt in current_options:
                    if isinstance(opt, str) and needs_latex(opt):
                        new_opt = fix_text(opt)
                        new_blank_options.append(new_opt)
                        blank_changed = True
                        if not apply:
                            logger.info(f"[DRY RUN] Q{q.id} Blank {blank_idx+1}: '{opt}' -> '{new_opt}'")
                    else:
                        new_blank_options.append(opt)
                
                new_answer_data.append(new_blank_options)
                if blank_changed:
                    changed = True
            
            if changed:
                updated_count += 1
                if apply:
                    q.answer = json.dumps(new_answer_data, ensure_ascii=False)
                    db.add(q)
                    logger.info(f"[APPLY] Updated Q{q.id}")
        
        if apply:
            await db.commit()
            logger.info(f"Successfully updated {updated_count} questions.")
        else:
            logger.info(f"Dry run complete. Found {updated_count} questions to update. Run with --apply to execute.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fix missing LaTeX in fill-in-the-blank answers")
    parser.add_argument("--apply", action="store_true", help="Apply changes to database")
    args = parser.parse_args()
    
    asyncio.run(main(args.apply))
