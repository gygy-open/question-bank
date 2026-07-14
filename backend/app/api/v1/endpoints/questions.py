from typing import Any, List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app import crud, schemas, models
from app.api import deps
from app.models.question import QuestionType, Question, QuestionStatus
from app.models.import_task import ImportTask, ImportTaskStatus
from app.services.question_service import question_service
from app.services.activity_logger import log_activity

router = APIRouter()

@router.get("", response_model=schemas.QuestionPage)
async def read_questions(
    db: deps.SessionDep,
    page: int = 1,
    size: int = 10,
    subject_id: Optional[int] = None,
    knowledge_point_id: Optional[int] = None,
    tag_ids: List[int] = Query(None),
    q_type: Optional[QuestionType] = None,
    difficulty: Optional[int] = None,
    status: Optional[str] = None,
    import_task_id: Optional[int] = None,
    import_task_name: Optional[str] = None,
    review_count: Optional[int] = None,
    creator_id: Optional[int] = None,
    reviewer_id: Optional[int] = None,
    keyword: Optional[str] = None,
    id: Optional[int] = None,
    ids: List[int] = Query(None),
    source: Optional[str] = None,
    root_only: bool = False,
) -> Any:
    skip = (page - 1) * size
    questions = await crud.question.get_multi_with_filters(
        db, 
        skip=skip, 
        limit=size,
        subject_id=subject_id,
        knowledge_point_id=knowledge_point_id,
        tag_ids=tag_ids,
        q_type=q_type,
        difficulty=difficulty,
        status=status,
        import_task_id=import_task_id,
        import_task_name=import_task_name,
        review_count=review_count,
        creator_id=creator_id,
        reviewer_id=reviewer_id,
        keyword=keyword,
        id=id,
        ids=ids,
        source=source,
        root_only=root_only
    )
    total = await crud.question.count_with_filters(
        db,
        subject_id=subject_id,
        knowledge_point_id=knowledge_point_id,
        tag_ids=tag_ids,
        q_type=q_type,
        difficulty=difficulty,
        status=status,
        import_task_id=import_task_id,
        import_task_name=import_task_name,
        review_count=review_count,
        creator_id=creator_id,
        reviewer_id=reviewer_id,
        keyword=keyword,
        id=id,
        ids=ids,
        source=source,
        root_only=root_only
    )
    
    import math
    return {
        "items": questions,
        "total": total,
        "page": page,
        "size": size,
        "pages": math.ceil(total / size) if size > 0 else 0
    }

@router.post("", response_model=schemas.Question)
async def create_question(
    *,
    db: deps.SessionDep,
    question_in: schemas.QuestionCreate,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    if not question_in.subject_id and current_user.subject_id:
        question_in.subject_id = current_user.subject_id
    question = await crud.question.create_with_tags(db=db, obj_in=question_in, user_id=current_user.id)
    return question

@router.post("/batch", response_model=List[schemas.Question])
async def create_questions_batch(
    *,
    db: deps.SessionDep,
    batch_in: schemas.QuestionBatchCreate,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    if not batch_in.questions:
        return []
        
    # Create Import Task
    description = batch_in.filename if batch_in.filename else f"Batch import of {len(batch_in.questions)} questions"
    
    import_task = ImportTask(
        user_id=current_user.id,
        description=description,
        source="smart_import",
        file_path=batch_in.file_path or "virtual",
        original_filename=batch_in.filename or "smart_import.json",
        file_type="json",
        status=ImportTaskStatus.COMPLETED
    )
    db.add(import_task)
    await db.commit()
    await db.refresh(import_task)

    # Pre-fetch all tag categories for AI suggested tags
    tag_categories_map = {}
    stmt = select(models.TagCategory)
    result = await db.execute(stmt)
    for cat in result.scalars().all():
        tag_categories_map[cat.slug] = cat

    created_questions = []
    
    async def create_recursive(question_in: schemas.QuestionCreate, parent_id: Optional[int] = None) -> models.Question:
        # Handle children separately
        children_in = question_in.children or []
        
        # Set parent_id if provided (overriding whatever was in question_in)
        if parent_id is not None:
            question_in.parent_id = parent_id
            
        if not question_in.subject_id and current_user.subject_id:
            question_in.subject_id = current_user.subject_id
            
        if not question_in.source and batch_in.filename:
            question_in.source = batch_in.filename

        question = await question_service.create_question(
            db=db,
            question_in=question_in,
            user_id=current_user.id,
            import_task_id=import_task.id
        )
        
        # Process children
        for child_in in children_in:
            await create_recursive(child_in, parent_id=question.id)
            
        return question

    for question_in in batch_in.questions:
        question = await create_recursive(question_in)
        created_questions.append(question)
        
    return created_questions

@router.get("/{id}", response_model=schemas.Question)
async def read_question(
    *,
    db: deps.SessionDep,
    id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    question = await crud.question.get(db=db, id=id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    return question

@router.put("/{id}", response_model=schemas.Question)
async def update_question(
    *,
    db: deps.SessionDep,
    id: int,
    question_in: schemas.QuestionUpdate,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    question = await crud.question.get(db=db, id=id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    
    # Check permissions
    if not current_user.is_superuser and question.created_by != current_user.id:
        # Allow reviewers to update status?
        pass
        
    question = await crud.question.update_with_tags(db=db, db_obj=question, obj_in=question_in, user_id=current_user.id)
    return question

@router.delete("/{id}", response_model=schemas.Question)
async def delete_question(
    *,
    db: deps.SessionDep,
    id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    question = await crud.question.get(db=db, id=id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
        
    if not current_user.is_superuser and question.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
        
    question = await crud.question.remove(db=db, id=id)
    
    # Log activity
    await log_activity(db, current_user.id, action="delete", resource_type="question", resource_id=id, details={"message": f"Deleted question {id}"})
    
    return question

@router.post("/batch-delete", response_model=Any)
async def delete_questions_batch(
    *,
    db: deps.SessionDep,
    delete_data: schemas.QuestionBatchDelete,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Batch delete questions.
    """
    if not delete_data.ids:
        return {"message": "No question IDs provided.", "deleted_count": 0}

    # Fetch questions to check permissions
    stmt = select(Question).where(Question.id.in_(delete_data.ids), Question.deleted_at.is_(None))
    result = await db.execute(stmt)
    questions = result.scalars().all()

    if not questions:
        return {"message": "No questions found with provided IDs.", "deleted_count": 0}

    deleted_count = 0
    for question in questions:
        if not current_user.is_superuser and question.created_by != current_user.id:
            # Skip questions user doesn't have permission to delete
            continue
            
        question.deleted_at = datetime.utcnow()
        question.updated_by = current_user.id
        db.add(question)
        deleted_count += 1
        
        # Log activity
        await log_activity(db, current_user.id, action="delete", resource_type="question", resource_id=question.id, details={"message": f"Batch deleted question {question.id}"})
    
    await db.commit()
    
    return {
        "message": f"Successfully deleted {deleted_count} questions.",
        "deleted_count": deleted_count
    }

@router.post("/batch-update", response_model=Any)
async def update_questions_batch(
    *,
    db: deps.SessionDep,
    update_data: schemas.QuestionBatchUpdate,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Batch update questions.
    """
    if not update_data.ids:
        return {"message": "No question IDs provided.", "updated_count": 0}

    # Fetch questions to check permissions
    stmt = select(Question).where(Question.id.in_(update_data.ids), Question.deleted_at.is_(None))
    result = await db.execute(stmt)
    questions = result.scalars().all()

    if not questions:
        return {"message": "No questions found with provided IDs.", "updated_count": 0}

    updated_count = 0
    for question in questions:
        if not current_user.is_superuser and question.created_by != current_user.id:
            # Skip questions user doesn't have permission to update
            continue
            
        if update_data.source is not None:
            question.source = update_data.source
            
        updated_count += 1
        
        # Log activity
        await log_activity(db, current_user.id, action="update", resource_type="question", resource_id=question.id, details={"message": f"Batch updated question {question.id}"})
    
    await db.commit()
    
    return {
        "message": f"Successfully updated {updated_count} questions.",
        "updated_count": updated_count
    }

@router.post("/batch-confirm", response_model=Any)
async def batch_confirm_questions(
    *,
    db: deps.SessionDep,
    confirm_data: schemas.QuestionBatchConfirm,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Batch confirm or reject question proposals.
    """
    if confirm_data.action not in ["approve", "reject"]:
        raise HTTPException(status_code=400, detail="Invalid action. Must be 'approve' or 'reject'.")

    if not confirm_data.question_ids:
        return {"message": "No question IDs provided."}

    # Fetch questions
    stmt = select(Question).where(Question.id.in_(confirm_data.question_ids), Question.deleted_at.is_(None))
    result = await db.execute(stmt)
    questions = result.scalars().all()

    if not questions:
        raise HTTPException(status_code=404, detail="No questions found with provided IDs.")

    processed_count = 0
    for question in questions:
        # Only process DRAFT questions to avoid accidental modification of existing questions
        if question.status == QuestionStatus.DRAFT:
            if confirm_data.action == "approve":
                question.status = QuestionStatus.PENDING
            elif confirm_data.action == "reject":
                question.deleted_at = datetime.utcnow()
                question.updated_by = current_user.id
                db.add(question)
            processed_count += 1
    
    await db.commit()
    
    return {
        "message": f"Successfully {confirm_data.action}d {processed_count} questions.",
        "processed_count": processed_count
    }
