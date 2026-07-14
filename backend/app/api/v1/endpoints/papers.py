import os
import logging
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask
from app.api import deps
from app.crud.crud_question import question as question_crud
from app.schemas.paper import PaperGenerateRequest
from app.services.paper_generator import paper_generator

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/download")
async def download_paper(
    request: PaperGenerateRequest,
    db: AsyncSession = Depends(deps.get_db),
) -> Any:
    """
    Generate and download a paper (docx or latex).
    """
    questions = await question_crud.get_multi_by_ids(db, ids=request.question_ids)
    if not questions:
        raise HTTPException(status_code=404, detail="No questions found")
                
    try:
        file_path = paper_generator.generate_file(
            request.title, 
            questions, 
            request.format,
            include_answer=request.include_answer,
            include_analysis=request.include_analysis,
            include_explanation=request.include_explanation,
            include_summary=request.include_summary,
            include_source=request.include_source
        )
        
        extension = request.format.value
        if extension == "latex":
            extension = "zip"
            
        filename = f"{request.title}.{extension}"
        
        def cleanup():
            if os.path.exists(file_path):
                os.remove(file_path)
                
        return FileResponse(
            path=file_path, 
            filename=filename, 
            background=BackgroundTask(cleanup)
        )
    except Exception as e:
        logger.error(f"Error generating paper: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
