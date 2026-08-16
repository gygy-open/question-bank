import os
import logging
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from app.api import deps
from app import crud, models
from app.schemas.publication import (
    PublicationCreate,
    PublicationUpdate,
    BlocksReplace,
    PublicationExportOptions,
    PublicationRead,
    PublicationDetail,
    BlockRead,
    QuestionBrief,
)
from app.services.publication_renderer import publication_renderer

logger = logging.getLogger(__name__)

router = APIRouter()


def _to_read(pub: models.Publication) -> PublicationRead:
    return PublicationRead(
        id=pub.id,
        pub_type=pub.pub_type,
        title=pub.title,
        description=pub.description,
        status=pub.status,
        difficulty=pub.difficulty,
        subject_id=pub.subject_id,
        owner_id=pub.owner_id,
        created_at=pub.created_at,
        updated_at=pub.updated_at,
        block_count=len(pub.blocks),
    )


def _to_detail(pub: models.Publication) -> PublicationDetail:
    blocks = [
        BlockRead(
            id=b.id,
            block_type=b.block_type,
            sequence=b.sequence,
            content=b.content,
            ref_question_id=b.ref_question_id,
            question=QuestionBrief.model_validate(b.question) if b.question else None,
        )
        for b in pub.blocks
    ]
    return PublicationDetail(
        id=pub.id,
        pub_type=pub.pub_type,
        title=pub.title,
        description=pub.description,
        status=pub.status,
        difficulty=pub.difficulty,
        subject_id=pub.subject_id,
        owner_id=pub.owner_id,
        created_at=pub.created_at,
        updated_at=pub.updated_at,
        block_count=len(blocks),
        blocks=blocks,
        knowledge_point_ids=[kp.id for kp in pub.knowledge_points],
    )


@router.get("", response_model=List[PublicationRead])
async def list_publications(
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
    pub_type: Optional[str] = None,
    subject_id: Optional[int] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    knowledge_point_ids: Optional[List[int]] = Query(default=None),
    difficulty: Optional[int] = None,
    sort: str = "updated_desc",
    skip: int = 0,
    limit: int = 100,
) -> Any:
    pubs = await crud.publication.get_multi_by_owner(
        db,
        owner_id=current_user.id,
        pub_type=pub_type,
        subject_id=subject_id,
        status=status,
        keyword=keyword,
        knowledge_point_ids=knowledge_point_ids,
        difficulty=difficulty,
        sort=sort,
        skip=skip,
        limit=limit,
    )
    return [_to_read(p) for p in pubs]


@router.post("", response_model=PublicationRead)
async def create_publication(
    *,
    db: deps.SessionDep,
    pub_in: PublicationCreate,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    if not pub_in.subject_id:
        pub_in.subject_id = current_user.last_active_subject_id or current_user.subject_id
    pub = await crud.publication.create_for_owner(db, obj_in=pub_in, owner_id=current_user.id)
    return _to_read(pub)


@router.get("/{pub_id}", response_model=PublicationDetail)
async def get_publication(
    *,
    db: deps.SessionDep,
    pub_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    pub = await crud.publication.get_detail(db, pub_id=pub_id, owner_id=current_user.id)
    if not pub:
        raise HTTPException(status_code=404, detail="Publication not found")
    return _to_detail(pub)


@router.patch("/{pub_id}", response_model=PublicationRead)
async def update_publication(
    *,
    db: deps.SessionDep,
    pub_id: int,
    pub_in: PublicationUpdate,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    pub = await crud.publication.get_owned(db, pub_id=pub_id, owner_id=current_user.id)
    if not pub:
        raise HTTPException(status_code=404, detail="Publication not found")
    pub = await crud.publication.update_with_relations(db, db_obj=pub, obj_in=pub_in)
    return _to_read(pub)


@router.delete("/{pub_id}")
async def delete_publication(
    *,
    db: deps.SessionDep,
    pub_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    pub = await crud.publication.get_owned(db, pub_id=pub_id, owner_id=current_user.id)
    if not pub:
        raise HTTPException(status_code=404, detail="Publication not found")
    await db.delete(pub)
    await db.commit()
    return {"ok": True}


@router.post("/{pub_id}/duplicate", response_model=PublicationRead)
async def duplicate_publication(
    *,
    db: deps.SessionDep,
    pub_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    pub = await crud.publication.get_owned(db, pub_id=pub_id, owner_id=current_user.id)
    if not pub:
        raise HTTPException(status_code=404, detail="Publication not found")
    new_pub = await crud.publication.duplicate(db, publication=pub)
    return _to_read(new_pub)


@router.put("/{pub_id}/blocks", response_model=PublicationDetail)
async def replace_blocks(
    *,
    db: deps.SessionDep,
    pub_id: int,
    payload: BlocksReplace,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    pub = await crud.publication.get_owned(db, pub_id=pub_id, owner_id=current_user.id)
    if not pub:
        raise HTTPException(status_code=404, detail="Publication not found")
    await crud.publication.replace_blocks(db, publication=pub, blocks=payload.blocks)
    pub = await crud.publication.get_detail(db, pub_id=pub_id, owner_id=current_user.id)
    return _to_detail(pub)


@router.post("/{pub_id}/blocks/questions", response_model=PublicationDetail)
async def add_question_blocks(
    *,
    db: deps.SessionDep,
    pub_id: int,
    payload: dict,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """将若干题目作为题块追加到队尾 (试题篮加入题目)。"""
    question_ids = payload.get("question_ids") or []
    pub = await crud.publication.get_owned(db, pub_id=pub_id, owner_id=current_user.id)
    if not pub:
        raise HTTPException(status_code=404, detail="Publication not found")
    await crud.publication.append_question_blocks(db, publication=pub, question_ids=question_ids)
    pub = await crud.publication.get_detail(db, pub_id=pub_id, owner_id=current_user.id)
    return _to_detail(pub)


@router.post("/{pub_id}/blocks/import-group/{group_id}", response_model=PublicationDetail)
async def import_group(
    *,
    db: deps.SessionDep,
    pub_id: int,
    group_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """柔性解包: 将题组的块深拷贝追加到目标出版物队尾。"""
    target = await crud.publication.get_owned(db, pub_id=pub_id, owner_id=current_user.id)
    if not target:
        raise HTTPException(status_code=404, detail="Publication not found")
    group = await crud.publication.get_owned(db, pub_id=group_id, owner_id=current_user.id)
    if not group:
        raise HTTPException(status_code=404, detail="Question group not found")
    await crud.publication.import_group_blocks(db, target=target, group=group)
    target = await crud.publication.get_detail(db, pub_id=pub_id, owner_id=current_user.id)
    return _to_detail(target)


@router.post("/{pub_id}/download")
async def download_publication(
    *,
    db: deps.SessionDep,
    pub_id: int,
    options: PublicationExportOptions,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """Generate and download a publication preserving block order."""
    pub = await crud.publication.get_owned(db, pub_id=pub_id, owner_id=current_user.id)
    if not pub:
        raise HTTPException(status_code=404, detail="Publication not found")

    blocks = await crud.publication.get_ordered_blocks(db, pub_id=pub_id)
    if not blocks:
        raise HTTPException(status_code=404, detail="Publication has no content")

    title = options.title or pub.title
    try:
        file_path = publication_renderer.generate_file(
            title,
            blocks,
            options.format,
            content_position=options.content_position,
            include_answer=options.include_answer,
            include_analysis=options.include_analysis,
            include_explanation=options.include_explanation,
            include_summary=options.include_summary,
            include_source=options.include_source,
        )

        extension = options.format.value
        if extension == "latex":
            extension = "zip"
        filename = f"{title}.{extension}"

        def cleanup():
            if os.path.exists(file_path):
                os.remove(file_path)

        return FileResponse(
            path=file_path,
            filename=filename,
            background=BackgroundTask(cleanup),
        )
    except Exception as e:
        logger.error(f"Error generating publication: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
