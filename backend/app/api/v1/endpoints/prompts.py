from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.api import deps
from app.crud.crud_prompt import prompt_template
from app.schemas.prompt import PromptTemplate, PromptTemplateCreate, PromptTemplateUpdate
from app.models.user import User

router = APIRouter()

@router.get("", response_model=List[PromptTemplate])
async def read_prompts(
    db: AsyncSession = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Retrieve prompt templates.
    """
    prompts = await prompt_template.get_by_user(db, user_id=current_user.id, skip=skip, limit=limit)
    return prompts

@router.post("", response_model=PromptTemplate)
async def create_prompt(
    *,
    db: AsyncSession = Depends(deps.get_db),
    prompt_in: PromptTemplateCreate,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Create new prompt template.
    """
    prompt = await prompt_template.create(db, obj_in=prompt_in, user_id=current_user.id)
    return prompt

@router.put("/{id}", response_model=PromptTemplate)
async def update_prompt(
    *,
    db: AsyncSession = Depends(deps.get_db),
    id: int,
    prompt_in: PromptTemplateUpdate,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Update a prompt template.
    """
    prompt = await prompt_template.get(db, id=id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt template not found")
    if prompt.user_id != current_user.id:
        raise HTTPException(status_code=400, detail="Not enough permissions")
    prompt = await prompt_template.update(db, db_obj=prompt, obj_in=prompt_in)
    return prompt

@router.delete("/{id}", response_model=PromptTemplate)
async def delete_prompt(
    *,
    db: AsyncSession = Depends(deps.get_db),
    id: int,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Delete a prompt template.
    """
    prompt = await prompt_template.get(db, id=id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt template not found")
    if prompt.user_id != current_user.id:
        raise HTTPException(status_code=400, detail="Not enough permissions")
    prompt = await prompt_template.remove(db, id=id)
    return prompt
