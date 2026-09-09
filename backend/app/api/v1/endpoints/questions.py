from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from app import crud, schemas, models
from app.api import deps
from app import capabilities
from app.capabilities import questions as question_caps
from app.crud.crud_question import is_question_visible
from app.models.question import QuestionType, QuestionStatus
from app.models.import_task import ImportTask, ImportTaskStatus
from app.services.importing.contracts import ImportDefaults
from app.services.importing.normalize import question_importer

router = APIRouter()


@router.get("", response_model=schemas.QuestionPage)
async def read_questions(
    db: deps.SessionDep,
    page: int = 1,
    size: int = 10,
    subject_id: Optional[int] = None,
    knowledge_point_ids: List[int] = Query(None),
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
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    skip = (page - 1) * size
    questions = await crud.question.get_multi_with_filters(
        db, 
        skip=skip, 
        limit=size,
        subject_id=subject_id,
        knowledge_point_ids=knowledge_point_ids,
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
        root_only=root_only,
        viewer=current_user
    )
    total = await crud.question.count_with_filters(
        db,
        subject_id=subject_id,
        knowledge_point_ids=knowledge_point_ids,
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
        root_only=root_only,
        viewer=current_user
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
    return await capabilities.run(
        "question.create", deps.api_context(db, current_user), question_in
    )

@router.post("/batch", response_model=List[schemas.Question])
async def create_questions_batch(
    *,
    db: deps.SessionDep,
    batch_in: schemas.QuestionBatchCreate,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    return await capabilities.run(
        "question.batch_create", deps.api_context(db, current_user), batch_in
    )

@router.post("/batch-legacy", response_model=schemas.LegacyBatchResult)
async def create_questions_batch_legacy(
    *,
    db: deps.SessionDep,
    batch_in: schemas.LegacyQuestionBatchCreate,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """智能导入工作台专用:接收旧字符串形态题目,后端统一经 adapter 转严格 v2 后落库。

    严格 QuestionCreate 不接受旧格式;前端不复制 Python 解析规则。无法解析的答案不静默
    写入 legacy_unresolved,而是按条上报到 failed。
    """
    if not batch_in.questions:
        return schemas.LegacyBatchResult()

    import_task = ImportTask(
        user_id=current_user.id,
        description=batch_in.filename or f"Batch import of {len(batch_in.questions)} questions",
        source="smart_import",
        file_path=batch_in.file_path or "virtual",
        original_filename=batch_in.filename or "smart_import.json",
        file_type="json",
        status=ImportTaskStatus.COMPLETED,
    )
    db.add(import_task)
    await db.commit()
    await db.refresh(import_task)

    raws = [item.model_dump() for item in batch_in.questions]
    defaults = ImportDefaults(
        subject_id=current_user.last_active_subject_id,
        status=QuestionStatus.PENDING,
        source=batch_in.filename,
    )
    report = await question_importer.import_batch(
        db,
        raws,
        user_id=current_user.id,
        import_task_id=import_task.id,
        defaults=defaults,
    )

    return schemas.LegacyBatchResult(
        import_task_id=import_task.id,
        created=report.created,
        failed=[
            schemas.LegacyBatchError(index=f.index, message=f.message)
            for f in report.failed
        ],
    )

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
    if not is_question_visible(question, current_user):
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
    return await capabilities.run(
        "question.update",
        deps.api_context(db, current_user),
        question_caps.QuestionUpdateInput(id=id, data=question_in),
    )

@router.post("/{id}/review", response_model=schemas.Question)
async def review_question(
    *,
    db: deps.SessionDep,
    id: int,
    review_in: schemas.QuestionReview,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    return await capabilities.run(
        "question.review",
        deps.api_context(db, current_user),
        question_caps.QuestionReviewInput(id=id, data=review_in),
    )

@router.delete("/{id}", response_model=schemas.Question)
async def delete_question(
    *,
    db: deps.SessionDep,
    id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    return await capabilities.run(
        "question.delete",
        deps.api_context(db, current_user),
        question_caps.QuestionIdInput(id=id),
    )

@router.post("/batch-delete", response_model=Any)
async def delete_questions_batch(
    *,
    db: deps.SessionDep,
    delete_data: schemas.QuestionBatchDelete,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    return await capabilities.run(
        "question.batch_delete", deps.api_context(db, current_user), delete_data
    )

@router.post("/batch-update", response_model=Any)
async def update_questions_batch(
    *,
    db: deps.SessionDep,
    update_data: schemas.QuestionBatchUpdate,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    return await capabilities.run(
        "question.batch_update", deps.api_context(db, current_user), update_data
    )

@router.post("/batch-confirm", response_model=Any)
async def batch_confirm_questions(
    *,
    db: deps.SessionDep,
    confirm_data: schemas.QuestionBatchConfirm,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    return await capabilities.run(
        "question.batch_confirm", deps.api_context(db, current_user), confirm_data
    )
