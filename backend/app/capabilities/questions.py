"""题目域能力 —— 写路径。

读路径(列表/详情)刻意不迁:可见性过滤已在 `crud_question` 的 `viewer=` 参数里做,
端点直连 CRUD 更直接。`POST /questions/batch-legacy` 是遗留兼容端点,同样不迁。

行为与迁移前的端点逐字一致(含「不可见 → 404 而非 403」、批量操作逐条跳过无权项)。
`question.batch_create` / `review` / `batch_confirm` 迁移前就没有任何鉴权,
本期只搬不改,登记在 UNGATED_ALLOWLIST 里。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel
from sqlalchemy import select

from app import crud, models, schemas
from app.core import permissions
from app.core.permissions import Permission
from app.crud.crud_question import is_question_visible
from app.models.import_task import ImportTask, ImportTaskStatus
from app.models.question import Question, QuestionStatus
from app.services.activity_logger import log_activity
from app.services.question_service import question_service

from .base import Authz, Capability, Scope
from .context import ExecutionContext
from .errors import Forbidden, Invalid, NotFound
from .registry import register


def can_delete_question(question: Question, user: models.User) -> bool:
    """删除权限:创建者 / 学科负责人 / 超管,且需对该题可见。"""
    if not is_question_visible(question, user):
        return False
    if user.is_superuser or question.created_by == user.id:
        return True
    return permissions.can(user, Permission.MANAGE_SUBJECT, subject_id=question.subject_id)


async def _load_visible_question(ctx: ExecutionContext, question_id: int) -> Question:
    question = await crud.question.get(db=ctx.db, id=question_id)
    if not question or not is_question_visible(question, ctx.actor):
        raise NotFound("Question not found")
    return question


class QuestionIdInput(BaseModel):
    id: int


class QuestionUpdateInput(BaseModel):
    id: int
    data: schemas.QuestionUpdate


class QuestionReviewInput(BaseModel):
    id: int
    data: schemas.QuestionReview


@register
class CreateQuestion(Capability[schemas.QuestionCreate, Question]):
    name = "question.create"
    description = "新建一道题目。"
    input_model = schemas.QuestionCreate
    authz = Authz.PERMISSION
    permission = Permission.EDIT_QUESTION
    scope = Scope.SUBJECT
    mutating = True

    def subject_for(self, ctx, inp, target) -> Optional[int]:
        return inp.subject_id or ctx.actor.last_active_subject_id

    async def execute(self, ctx: ExecutionContext, inp: schemas.QuestionCreate, target: Any) -> Question:
        inp.subject_id = self.subject_for(ctx, inp, target)
        return await crud.question.create_with_tags(db=ctx.db, obj_in=inp, user_id=ctx.actor.id)


@register
class BatchCreateQuestions(Capability[schemas.QuestionBatchCreate, List[Question]]):
    name = "question.batch_create"
    description = "批量创建题目(智能导入落库),同时登记一条已完成的导入任务。"
    input_model = schemas.QuestionBatchCreate
    authz = Authz.NONE
    scope = Scope.SUBJECT
    mutating = True

    async def execute(
        self, ctx: ExecutionContext, inp: schemas.QuestionBatchCreate, target: Any
    ) -> List[Question]:
        if not inp.questions:
            return []

        description = inp.filename if inp.filename else f"Batch import of {len(inp.questions)} questions"
        import_task = ImportTask(
            user_id=ctx.actor.id,
            description=description,
            source="smart_import",
            file_path=inp.file_path or "virtual",
            original_filename=inp.filename or "smart_import.json",
            file_type="json",
            status=ImportTaskStatus.COMPLETED,
        )
        ctx.db.add(import_task)
        await ctx.db.commit()
        await ctx.db.refresh(import_task)

        async def create_recursive(
            question_in: schemas.QuestionCreate, parent_id: Optional[int] = None
        ) -> Question:
            children_in = question_in.children or []
            if parent_id is not None:
                question_in.parent_id = parent_id
            if not question_in.subject_id:
                question_in.subject_id = ctx.actor.last_active_subject_id
            if not question_in.source and inp.filename:
                question_in.source = inp.filename

            question = await question_service.create_question(
                db=ctx.db,
                question_in=question_in,
                user_id=ctx.actor.id,
                import_task_id=import_task.id,
            )
            for child_in in children_in:
                await create_recursive(child_in, parent_id=question.id)
            return question

        return [await create_recursive(question_in) for question_in in inp.questions]


@register
class UpdateQuestion(Capability[QuestionUpdateInput, Question]):
    name = "question.update"
    description = "更新一道题目的内容、标签与知识点。"
    input_model = QuestionUpdateInput
    authz = Authz.PERMISSION
    permission = Permission.EDIT_QUESTION
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: QuestionUpdateInput) -> Question:
        return await _load_visible_question(ctx, inp.id)

    async def execute(self, ctx: ExecutionContext, inp: QuestionUpdateInput, target: Question) -> Question:
        return await crud.question.update_with_tags(
            db=ctx.db, db_obj=target, obj_in=inp.data, user_id=ctx.actor.id
        )


@register
class ReviewQuestion(Capability[QuestionReviewInput, Question]):
    name = "question.review"
    description = "审核一道题目:通过则累加审核次数并按学科阈值决定是否发布;驳回则退回草稿。"
    input_model = QuestionReviewInput
    authz = Authz.NONE
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: QuestionReviewInput) -> Question:
        question = await crud.question.get(db=ctx.db, id=inp.id)
        if not question:
            raise NotFound("Question not found")
        return question

    async def execute(self, ctx: ExecutionContext, inp: QuestionReviewInput, target: Question) -> Question:
        if inp.data.action == "approve":
            target.review_count = (target.review_count or 0) + 1
            # 是否发布由后端依据学科所需审核次数决定，前端不感知审核进度。
            required_count = target.subject.required_review_count if target.subject else 1
            if target.review_count >= required_count:
                target.status = QuestionStatus.PUBLISHED.value
            elif target.status == QuestionStatus.DRAFT.value:
                target.status = QuestionStatus.PENDING.value
        else:
            # 驳回:退回草稿重新编辑，审核次数清零重新计数。
            target.status = QuestionStatus.DRAFT.value
            target.review_count = 0

        target.updated_by = ctx.actor.id
        ctx.db.add(target)

        await log_activity(
            ctx.db,
            ctx.actor.id,
            action="review",
            resource_type="question",
            resource_id=inp.id,
            details={
                "action": inp.data.action,
                "comment": inp.data.comment,
                "resulting_status": target.status,
            },
        )

        await ctx.db.commit()
        return await crud.question.get(db=ctx.db, id=inp.id)


@register
class DeleteQuestion(Capability[QuestionIdInput, Question]):
    name = "question.delete"
    description = "软删除一道题目。仅创建者、学科负责人或超管可执行。"
    input_model = QuestionIdInput
    authz = Authz.CUSTOM
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: QuestionIdInput) -> Question:
        return await _load_visible_question(ctx, inp.id)

    async def authorize(self, ctx: ExecutionContext, inp: QuestionIdInput, target: Question) -> None:
        if not can_delete_question(target, ctx.actor):
            raise Forbidden("Not enough permissions")

    async def execute(self, ctx: ExecutionContext, inp: QuestionIdInput, target: Question) -> Question:
        question = await crud.question.remove(db=ctx.db, id=inp.id)
        await log_activity(
            ctx.db,
            ctx.actor.id,
            action="delete",
            resource_type="question",
            resource_id=inp.id,
            details={"message": f"Deleted question {inp.id}"},
        )
        return question


async def _load_questions_by_ids(ctx: ExecutionContext, ids: List[int]) -> List[Question]:
    stmt = select(Question).where(Question.id.in_(ids), Question.deleted_at.is_(None))
    result = await ctx.db.execute(stmt)
    return list(result.scalars().all())


@register
class BatchDeleteQuestions(Capability[schemas.QuestionBatchDelete, dict]):
    name = "question.batch_delete"
    description = "批量软删除题目;无权删除的条目会被跳过而非报错。"
    input_model = schemas.QuestionBatchDelete
    authz = Authz.CUSTOM
    scope = Scope.SUBJECT
    mutating = True

    async def execute(self, ctx: ExecutionContext, inp: schemas.QuestionBatchDelete, target: Any) -> dict:
        if not inp.ids:
            return {"message": "No question IDs provided.", "deleted_count": 0}

        questions = await _load_questions_by_ids(ctx, inp.ids)
        if not questions:
            return {"message": "No questions found with provided IDs.", "deleted_count": 0}

        deleted_count = 0
        for question in questions:
            if not can_delete_question(question, ctx.actor):
                continue
            question.deleted_at = datetime.utcnow()
            question.updated_by = ctx.actor.id
            ctx.db.add(question)
            deleted_count += 1
            await log_activity(
                ctx.db,
                ctx.actor.id,
                action="delete",
                resource_type="question",
                resource_id=question.id,
                details={"message": f"Batch deleted question {question.id}"},
            )

        await ctx.db.commit()
        return {
            "message": f"Successfully deleted {deleted_count} questions.",
            "deleted_count": deleted_count,
        }


@register
class BatchUpdateQuestions(Capability[schemas.QuestionBatchUpdate, dict]):
    name = "question.batch_update"
    description = "批量更新题目来源;非本人创建的条目会被跳过。"
    input_model = schemas.QuestionBatchUpdate
    authz = Authz.CUSTOM
    scope = Scope.SUBJECT
    mutating = True

    async def execute(self, ctx: ExecutionContext, inp: schemas.QuestionBatchUpdate, target: Any) -> dict:
        if not inp.ids:
            return {"message": "No question IDs provided.", "updated_count": 0}

        questions = await _load_questions_by_ids(ctx, inp.ids)
        if not questions:
            return {"message": "No questions found with provided IDs.", "updated_count": 0}

        updated_count = 0
        for question in questions:
            if not ctx.actor.is_superuser and question.created_by != ctx.actor.id:
                continue
            if inp.source is not None:
                question.source = inp.source
            updated_count += 1
            await log_activity(
                ctx.db,
                ctx.actor.id,
                action="update",
                resource_type="question",
                resource_id=question.id,
                details={"message": f"Batch updated question {question.id}"},
            )

        await ctx.db.commit()
        return {
            "message": f"Successfully updated {updated_count} questions.",
            "updated_count": updated_count,
        }


@register
class BatchConfirmQuestions(Capability[schemas.QuestionBatchConfirm, dict]):
    name = "question.batch_confirm"
    description = "批量确认或驳回草稿题目:确认转待审,驳回则软删除。"
    input_model = schemas.QuestionBatchConfirm
    authz = Authz.NONE
    scope = Scope.SUBJECT
    mutating = True

    async def execute(self, ctx: ExecutionContext, inp: schemas.QuestionBatchConfirm, target: Any) -> dict:
        if inp.action not in ["approve", "reject"]:
            raise Invalid("Invalid action. Must be 'approve' or 'reject'.")

        if not inp.question_ids:
            return {"message": "No question IDs provided."}

        questions = await _load_questions_by_ids(ctx, inp.question_ids)
        if not questions:
            raise NotFound("No questions found with provided IDs.")

        processed_count = 0
        for question in questions:
            # 只处理草稿，避免误改已入库题目。
            if question.status == QuestionStatus.DRAFT:
                if inp.action == "approve":
                    question.status = QuestionStatus.PENDING
                elif inp.action == "reject":
                    question.deleted_at = datetime.utcnow()
                    question.updated_by = ctx.actor.id
                    ctx.db.add(question)
                processed_count += 1

        await ctx.db.commit()
        return {
            "message": f"Successfully {inp.action}d {processed_count} questions.",
            "processed_count": processed_count,
        }
