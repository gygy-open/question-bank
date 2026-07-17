import asyncio
import logging
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

# Add backend directory to path so we can import app modules
sys.path.append(str(Path(__file__).parent.parent))

from app.db.session import SessionLocal
from app.core.config import get_db_url, is_configured
from app.models.import_task import ImportTask, ImportTaskStatus
from app.models.question import QuestionStatus, QuestionType
from app.models.user import User
from app.schemas.question import QuestionCreate
from app.services.doc_processor import doc_processor
from app.services.embedding import reload_embedding_function
from app.services.question_service import question_service

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def process_task(db: AsyncSession, task: ImportTask):
    try:
        logger.info(f"Starting task {task.id} ({task.file_type}): {task.original_filename}")
        
        # Update status to PROCESSING
        task.status = ImportTaskStatus.PROCESSING
        task.updated_at = datetime.now(timezone.utc)
        db.add(task)
        await db.commit()
        await db.refresh(task)
        logger.info(f"Task {task.id} status updated to PROCESSING")
        
        # Process file
        file_path = Path(task.file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
            
        result = None
        if task.file_type == 'docx':
            import uuid
            proc_task_id = str(uuid.uuid4())
            result = await doc_processor.process_docx(file_path, db=db, task_id=proc_task_id, mode=task.mode or "extract")
        elif task.file_type == 'markdown':
            content = file_path.read_text(encoding='utf-8')
            import uuid
            proc_task_id = str(uuid.uuid4())
            result = await doc_processor.process_markdown(content, db=db, filename=task.original_filename, task_id=proc_task_id, mode=task.mode or "extract")
            
        if result:
            # Save questions
            questions_data = result.get("questions", [])
            saved_count = 0
            
            creator_id = task.user_id
            
            # Fetch user to get subject_id
            subject_id = None
            if creator_id:
                user_stmt = select(User).where(User.id == creator_id)
                user_result = await db.execute(user_stmt)
                user = user_result.scalar_one_or_none()
                if user:
                    subject_id = user.subject_id
            
            for q_data in questions_data:
                # Determine type enum
                q_type_str = q_data.get("q_type", q_data.get("type", "single_choice")).lower()
                q_type = QuestionType.SINGLE_CHOICE
                
                if "multiple" in q_type_str: 
                    q_type = QuestionType.MULTIPLE_CHOICE
                elif "true" in q_type_str or "false" in q_type_str: 
                    q_type = QuestionType.TRUE_FALSE
                elif "fill" in q_type_str or "blank" in q_type_str or "填空" in q_type_str: 
                    q_type = QuestionType.FILL_IN_THE_BLANK
                elif "free" in q_type_str or "response" in q_type_str or "essay" in q_type_str or "解答" in q_type_str or "short" in q_type_str: 
                    q_type = QuestionType.FREE_RESPONSE
                
                # Handle answer format
                answer_val = q_data.get("answer")
                if q_type == QuestionType.FILL_IN_THE_BLANK:
                    # Ensure answer is JSON string of List[List[str]]
                    if isinstance(answer_val, list):
                        # If it's a flat list [ans1, ans2], convert to [[ans1], [ans2]]
                        # If it's already [[ans1], [ans2]], keep it
                        # If it's [ans1, [ans2]], normalize
                        normalized_ans = []
                        for item in answer_val:
                            if isinstance(item, list):
                                normalized_ans.append([str(i) for i in item])
                            else:
                                normalized_ans.append([str(item)])
                        answer_val = json.dumps(normalized_ans, ensure_ascii=False)
                    elif isinstance(answer_val, str):
                        # If it's a string, try to parse it or wrap it
                        try:
                            parsed = json.loads(answer_val)
                            if isinstance(parsed, list):
                                # Normalize structure to List[List[str]]
                                normalized_ans = []
                                for item in parsed:
                                    if isinstance(item, list):
                                        normalized_ans.append([str(i) for i in item])
                                    else:
                                        normalized_ans.append([str(item)])
                                answer_val = json.dumps(normalized_ans, ensure_ascii=False)
                            else:
                                # Parsed but not a list (e.g. number, quoted string, boolean, dict)
                                # Treat as single blank content
                                answer_val = json.dumps([[str(parsed)]], ensure_ascii=False)
                        except:
                            # Treat as single blank
                            answer_val = json.dumps([[answer_val]], ensure_ascii=False)
                    elif answer_val is not None:
                        # Handle other types (int, float, dict, etc.) by wrapping them
                        answer_val = json.dumps([[str(answer_val)]], ensure_ascii=False)
                else:
                    # For other types, ensure it's a string
                    if isinstance(answer_val, (list, dict)):
                        answer_val = json.dumps(answer_val, ensure_ascii=False)
                    elif answer_val is not None:
                        answer_val = str(answer_val)

                # Prepare AI suggested tags
                ai_suggested_tags = {}
                if q_data.get("tags"):
                    ai_suggested_tags["ai_extracted"] = q_data.get("tags")


                # Prepare Knowledge Point IDs
                raw_kp_ids = q_data.get("knowledge_point_ids")
                kp_ids = []
                if raw_kp_ids:
                    try:
                        kp_ids = [int(i) for i in raw_kp_ids]
                    except Exception:
                        kp_ids = []

                # Create Question Schema
                question_in = QuestionCreate(
                    content=q_data.get("content"),
                    options=q_data.get("options"),
                    answer=answer_val,
                    thinking=q_data.get("thinking"),
                    analysis=q_data.get("analysis"),
                    summary=q_data.get("summary"),
                    q_type=q_type,
                    status=QuestionStatus.PENDING,
                    difficulty=q_data.get("difficulty", 1),
                    subject_id=subject_id,
                    knowledge_point_ids=kp_ids,
                    ai_suggested_tags=ai_suggested_tags,
                    source=task.original_filename
                )

                await question_service.create_question(
                    db=db,
                    question_in=question_in,
                    user_id=creator_id,
                    import_task_id=task.id
                )

                saved_count += 1
            
            task.result_summary = json.dumps({"count": saved_count, "proc_task_id": result.get("task_id")})
            task.status = ImportTaskStatus.COMPLETED
            logger.info(f"Task {task.id} completed. Saved {saved_count} questions.")
        else:
            task.status = ImportTaskStatus.FAILED
            task.error_message = "No result from processor"
            logger.error(f"Task {task.id} failed: No result")
            
    except Exception as e:
        logger.error(f"Error processing task {task.id}: {e}", exc_info=True)
        task.status = ImportTaskStatus.FAILED
        task.error_message = str(e)

        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            logger.critical("Quota exceeded (429), stopping worker...")
            raise SystemExit(1)
    finally:
        task.updated_at = datetime.now(timezone.utc)
        await db.commit()

async def worker():
    logger.info("Worker started, initializing...")

    # In a packaged desktop build the worker is spawned before the first-run
    # setup wizard has picked a database. Wait until the app is configured
    # before touching the DB or the embedding model.
    while not is_configured():
        logger.info("Worker: database not configured yet, waiting for setup...")
        await asyncio.sleep(5)

    # Initialize Embedding Function
    try:
        await reload_embedding_function()
        logger.info("Embedding function initialized.")
    except Exception as e:
        logger.error(f"Failed to initialize embedding function: {e}")

    logger.info("Worker waiting for tasks...")
    # SQLite does not support ``SELECT ... FOR UPDATE SKIP LOCKED``. In the
    # single-writer SQLite (desktop) case there is only one worker anyway, so
    # row-level locking is unnecessary; on MySQL we keep SKIP LOCKED so multiple
    # workers can pull tasks concurrently without contention.
    use_row_lock = not get_db_url().startswith("sqlite")
    while True:
        async with SessionLocal() as db:
            try:
                # SKIP LOCKED query
                stmt = select(ImportTask).where(
                    ImportTask.status == ImportTaskStatus.PENDING,
                    ImportTask.source == "batch_upload"
                )\
                    .order_by(ImportTask.created_at)\
                    .limit(1)
                if use_row_lock:
                    stmt = stmt.with_for_update(skip_locked=True)
                
                result = await db.execute(stmt)
                task = result.scalar_one_or_none()
                
                if task:
                    await process_task(db, task)
                else:
                    await db.commit()
                    await asyncio.sleep(10)
            except Exception as e:
                logger.error(f"Worker loop error: {e}")
                await asyncio.sleep(5)

def main():
    """Blocking entry point. Importable so the packaged desktop launcher can run
    the worker in a child process (see the packaging plan)."""
    asyncio.run(worker())


if __name__ == "__main__":
    main()
