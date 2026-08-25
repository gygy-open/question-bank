import asyncio
import logging
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from sqlalchemy import select, update, func, text
from sqlalchemy.ext.asyncio import AsyncSession

# Add backend directory to path so we can import app modules
sys.path.append(str(Path(__file__).parent.parent))

from app.db.session import SessionLocal
from app.core.config import get_db_url, is_configured
from app.models.import_task import ImportTask, ImportTaskStatus
from app.models.question import QuestionStatus
from app.models.user import User
from app.services.doc_processor import doc_processor
from app.services.embedding import reload_embedding_function
from app.services.importing.contracts import ImportDefaults
from app.services.importing.normalize import question_importer

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

        # Resolve subject up-front so knowledge-point retrieval can be subject-scoped.
        subject_id = None
        if task.user_id:
            user_stmt = select(User).where(User.id == task.user_id)
            user_result = await db.execute(user_stmt)
            user = user_result.scalar_one_or_none()
            if user:
                subject_id = user.last_active_subject_id or user.subject_id

        result = None
        if task.file_type == 'docx':
            import uuid
            proc_task_id = str(uuid.uuid4())
            result = await doc_processor.process_docx(file_path, db=db, task_id=proc_task_id, mode=task.mode or "extract", subject_id=subject_id)
        elif task.file_type == 'markdown':
            content = file_path.read_text(encoding='utf-8')
            import uuid
            proc_task_id = str(uuid.uuid4())
            result = await doc_processor.process_markdown(content, db=db, filename=task.original_filename, task_id=proc_task_id, mode=task.mode or "extract", subject_id=subject_id)
            
        if result:
            # Save questions via the shared importer (same path as /questions/batch-legacy).
            questions_data = result.get("questions", [])
            defaults = ImportDefaults(
                subject_id=subject_id,
                status=QuestionStatus.PENDING,
                source=task.original_filename,
            )
            report = await question_importer.import_batch(
                db,
                questions_data,
                user_id=task.user_id,
                import_task_id=task.id,
                defaults=defaults,
            )

            task.result_summary = json.dumps(
                {
                    "count": report.saved_count,
                    "failed": report.failed_count,
                    "proc_task_id": result.get("task_id"),
                }
            )
            task.status = ImportTaskStatus.COMPLETED
            logger.info(
                f"Task {task.id} completed. Saved {report.saved_count} questions, "
                f"{report.failed_count} skipped (un-adaptable)."
            )
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

async def wait_for_schema() -> None:
    """Block until the database schema has been migrated.

    ``is_configured()`` only tells us a database URL exists — the tables may not
    be there yet because migrations run in a *different* process (the backend
    entrypoint / the setup wizard) and can still be in progress. Probing a core
    table here prevents the worker from querying (and erroring on) tables that
    have not been created yet.
    """
    while True:
        try:
            async with SessionLocal() as db:
                await db.execute(text("SELECT 1 FROM import_tasks LIMIT 1"))
            return
        except Exception:
            logger.info("Worker: waiting for database schema (migrations)...")
            await asyncio.sleep(5)


async def worker():
    logger.info("Worker started, initializing...")

    # In a packaged desktop build the worker is spawned before the first-run
    # setup wizard has picked a database. Wait until the app is configured
    # before touching the DB or the embedding model.
    while not is_configured():
        logger.info("Worker: database not configured yet, waiting for setup...")
        await asyncio.sleep(5)

    # A configured URL does not guarantee the schema exists yet: migrations may
    # still be running in another process. Wait for the tables before touching
    # the DB or the embedding model (which reads ``system_settings``).
    await wait_for_schema()

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
