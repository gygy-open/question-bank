"""题目域能力 —— 写路径。

读路径(列表/详情)刻意不迁:可见性过滤已在 `crud_question` 的 `viewer=` 参数里做,
端点直连 CRUD 更直接。`POST /questions/batch-legacy` 是遗留兼容端点,同样不迁。

行为与迁移前的端点逐字一致(含「不可见 → 404 而非 403」、批量操作逐条跳过无权项)。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel
from sqlalchemy import select

from app import crud, models, schemas
from app.core import permissions
from app.core.permissions import Permission
from app.crud.crud_question import is_question_visible, release_stimulus_slot
from app.core.file_paths import sanitize_client_source_path
from app.models.import_task import ImportTask, ImportTaskStatus
from app.models.question import Question, QuestionStatus
from app.models.question_relation import QuestionRelation, QuestionRelationType
from app.services.activity_logger import log_activity
from app.services.question_relation_service import (
    create_question_relation,
    delete_question_relation,
)
from app.services.question_service import question_service
from app.core.api_errors import ErrorCode

from .base import Authz, Capability, Scope
from .context import ExecutionContext
from .errors import DuplicateSuspected, Forbidden, Invalid, NotFound
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
        raise NotFound("Question not found", ErrorCode.QUESTION_NOT_FOUND)
    return question


async def ensure_not_duplicate(
    ctx: ExecutionContext,
    *,
    subject_id: Optional[int],
    q_type: Any,
    content: Any,
    options: Any = None,
    stimulus_id: Optional[int] = None,
    exclude_ids: tuple = (),
) -> None:
    """题库中已有重复/高度相似题时抛 DuplicateSuspected;调用方确认后带 allow_duplicate 重试。"""
    from app.services import question_dedup

    key = question_dedup.key_from_payload(
        q_type=q_type,
        content=content,
        options=options,
        stimulus_content=await question_dedup.stimulus_content(ctx.db, stimulus_id),
    )
    found = await question_dedup.find_duplicates(
        ctx.db, viewer=ctx.actor, subject_id=subject_id, key=key, exclude_ids=exclude_ids
    )
    if found:
        raise DuplicateSuspected({"candidates": question_dedup.candidates_payload(found)})


class QuestionIdInput(BaseModel):
    id: int


class QuestionUpdateInput(BaseModel):
    id: int
    data: schemas.QuestionUpdate


class QuestionReviewInput(BaseModel):
    id: int
    data: schemas.QuestionReview


class QuestionRelationInput(BaseModel):
    source_question_id: int
    target_question_id: int


class DerivedQuestionCreateInput(BaseModel):
    source_question_id: int
    data: schemas.QuestionCreate


@register
class CreateQuestion(Capability[schemas.QuestionCreate, Question]):
    name = "question.create"
    description = "Create a question. New questions are drafts unless a status is given; subject_id defaults to the user's last active subject."
    input_model = schemas.QuestionCreate
    authz = Authz.PERMISSION
    permission = Permission.EDIT_QUESTION
    scope = Scope.SUBJECT
    mutating = True

    def subject_for(self, ctx, inp, target) -> Optional[int]:
        return inp.subject_id or ctx.actor.last_active_subject_id

    async def execute(self, ctx: ExecutionContext, inp: schemas.QuestionCreate, target: Any) -> Question:
        inp.subject_id = self.subject_for(ctx, inp, target)
        if not inp.allow_duplicate:
            await ensure_not_duplicate(
                ctx, subject_id=inp.subject_id, q_type=inp.q_type, content=inp.content, options=inp.options
            )
        return await crud.question.create_with_tags(db=ctx.db, obj_in=inp, user_id=ctx.actor.id)


@register
class CreateQuestionRelation(Capability[QuestionRelationInput, QuestionRelation]):
    name = "question.relation.create"
    description = "Link a source question to a derived question."
    input_model = QuestionRelationInput
    authz = Authz.PERMISSION
    permission = Permission.EDIT_QUESTION
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: QuestionRelationInput) -> Question:
        return await _load_visible_question(ctx, inp.source_question_id)

    async def execute(
        self, ctx: ExecutionContext, inp: QuestionRelationInput, target: Question
    ) -> QuestionRelation:
        return await create_question_relation(
            ctx.db,
            source_question_id=target.id,
            target_question_id=inp.target_question_id,
            actor=ctx.actor,
        )


@register
class DeleteQuestionRelation(Capability[QuestionRelationInput, None]):
    name = "question.relation.delete"
    description = "Unlink a source question from a derived question. Neither question is deleted."
    input_model = QuestionRelationInput
    authz = Authz.PERMISSION
    permission = Permission.EDIT_QUESTION
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: QuestionRelationInput) -> Question:
        return await _load_visible_question(ctx, inp.source_question_id)

    async def execute(
        self, ctx: ExecutionContext, inp: QuestionRelationInput, target: Question
    ) -> None:
        await delete_question_relation(
            ctx.db,
            source_question_id=target.id,
            target_question_id=inp.target_question_id,
            actor=ctx.actor,
        )


@register
class CreateDerivedQuestion(Capability[DerivedQuestionCreateInput, Question]):
    name = "question.derived.create"
    description = "Atomically create a derived question and link it to its source question."
    input_model = DerivedQuestionCreateInput
    authz = Authz.PERMISSION
    permission = Permission.EDIT_QUESTION
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: DerivedQuestionCreateInput) -> Question:
        return await _load_visible_question(ctx, inp.source_question_id)

    async def execute(
        self, ctx: ExecutionContext, inp: DerivedQuestionCreateInput, target: Question
    ) -> Question:
        question_in = inp.data.model_copy(deep=True)
        question_in.subject_id = target.subject_id
        if not question_in.allow_duplicate:
            await ensure_not_duplicate(
                ctx,
                subject_id=question_in.subject_id,
                q_type=question_in.q_type,
                content=question_in.content,
                options=question_in.options,
            )
        try:
            question = await question_service.create_question(
                db=ctx.db,
                question_in=question_in,
                user_id=ctx.actor.id,
                commit=False,
            )
            await create_question_relation(
                ctx.db,
                source_question_id=target.id,
                target_question_id=question.id,
                actor=ctx.actor,
                commit=False,
                new_target=True,
            )
            await ctx.db.commit()
            created = await crud.question.get(ctx.db, id=question.id)
            if created is None:
                raise NotFound("Question not found", ErrorCode.QUESTION_NOT_FOUND)
            return created
        except Exception:
            await ctx.db.rollback()
            raise


@register
class BatchCreateQuestions(Capability[schemas.QuestionBatchCreate, List[Question]]):
    name = "question.batch_create"
    description = "Create questions in bulk and record a completed import task for them."
    input_model = schemas.QuestionBatchCreate
    authz = Authz.CUSTOM
    scope = Scope.SUBJECT
    mutating = True

    async def authorize(self, ctx: ExecutionContext, inp: schemas.QuestionBatchCreate, target: Any) -> None:
        # 整批写入,任一题目的学科无编辑权就整批拒绝。
        pending = list(inp.questions)
        while pending:
            item = pending.pop()
            subject_id = item.subject_id or ctx.actor.last_active_subject_id
            if not permissions.can(ctx.actor, Permission.EDIT_QUESTION, subject_id=subject_id):
                raise Forbidden("The user doesn't have enough privileges", ErrorCode.AUTH_FORBIDDEN)
            pending.extend(item.children or [])

    async def execute(
        self, ctx: ExecutionContext, inp: schemas.QuestionBatchCreate, target: Any
    ) -> List[Question]:
        if not inp.questions:
            return []
        await self._check_duplicates(ctx, inp)

        description = inp.filename if inp.filename else f"Batch import of {len(inp.questions)} questions"
        import_task = ImportTask(
            user_id=ctx.actor.id,
            description=description,
            source="smart_import",
            file_path=sanitize_client_source_path(inp.file_path),
            original_filename=inp.filename or "smart_import.json",
            file_type="json",
            status=ImportTaskStatus.COMPLETED,
        )
        ctx.db.add(import_task)
        await ctx.db.flush()

        async def create_recursive(
            question_in: schemas.QuestionBatchItemCreate, parent_id: Optional[int] = None
        ) -> Question:
            children_in = question_in.children or []
            relation_source_id = parent_id or question_in.parent_id
            question_in.parent_id = None
            if not question_in.subject_id:
                question_in.subject_id = ctx.actor.last_active_subject_id
            if not question_in.source and inp.filename:
                question_in.source = inp.filename

            question = await question_service.create_question(
                db=ctx.db,
                question_in=question_in,
                user_id=ctx.actor.id,
                import_task_id=import_task.id,
                commit=False,
            )
            if relation_source_id is not None:
                ctx.db.add(
                    QuestionRelation(
                        source_question_id=relation_source_id,
                        target_question_id=question.id,
                        relation_type=QuestionRelationType.DECOMPOSED_FROM.value,
                        created_by=ctx.actor.id,
                    )
                )
            for child_in in children_in:
                await create_recursive(child_in, parent_id=question.id)
            return question

        created = [await create_recursive(question_in) for question_in in inp.questions]
        await ctx.db.commit()
        return created

    async def _check_duplicates(self, ctx: ExecutionContext, inp: schemas.QuestionBatchCreate) -> None:
        """整批检查(含批内互相重复);未放行的命中项一并报告,整批不写入。"""
        from app.services import question_dedup

        items: List[question_dedup.BatchItem] = []
        allowed: dict = {}
        subjects: dict = {}
        pending = [(str(i), q) for i, q in enumerate(inp.questions)]
        while pending:
            ref, item = pending.pop(0)
            ref = item.temp_id or ref
            subjects[ref] = item.subject_id or ctx.actor.last_active_subject_id
            allowed[ref] = item.allow_duplicate
            items.append(question_dedup.BatchItem(
                ref, question_dedup.key_from_payload(q_type=item.q_type, content=item.content, options=item.options)
            ))
            pending.extend((f"{ref}.{j}", child) for j, child in enumerate(item.children or []))

        flagged: List[dict] = []
        by_subject: dict = {}
        for it in items:
            by_subject.setdefault(subjects[it.ref], []).append(it)
        for subject_id, group in by_subject.items():
            existing, intra = await question_dedup.find_duplicates_batch(
                ctx.db, viewer=ctx.actor, subject_id=subject_id, items=group
            )
            for it in group:
                if allowed[it.ref] or (it.ref not in existing and it.ref not in intra):
                    continue
                flagged.append({
                    "ref": it.ref,
                    "candidates": question_dedup.candidates_payload(existing.get(it.ref, [])),
                    "batch": intra.get(it.ref, []),
                })
        if flagged:
            raise DuplicateSuspected({"items": flagged})


@register
class UpdateQuestion(Capability[QuestionUpdateInput, Question]):
    name = "question.update"
    description = "Update a question's content, tags and knowledge points."
    input_model = QuestionUpdateInput
    authz = Authz.PERMISSION
    permission = Permission.EDIT_QUESTION
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: QuestionUpdateInput) -> Question:
        return await _load_visible_question(ctx, inp.id)

    async def authorize(
        self, ctx: ExecutionContext, inp: QuestionUpdateInput, target: Question
    ) -> None:
        await super().authorize(ctx, inp, target)
        if (
            "subject_id" in inp.data.model_fields_set
            and inp.data.subject_id != target.subject_id
            and not permissions.can(
                ctx.actor,
                Permission.EDIT_QUESTION,
                subject_id=inp.data.subject_id,
            )
        ):
            raise Forbidden("The user doesn't have enough privileges", ErrorCode.AUTH_FORBIDDEN)

    async def execute(self, ctx: ExecutionContext, inp: QuestionUpdateInput, target: Question) -> Question:
        data = inp.data
        fields = data.model_fields_set
        if not data.allow_duplicate and fields & {"content", "options", "q_type", "subject_id"}:
            from app.services import question_dedup

            subject_id = data.subject_id if "subject_id" in fields else target.subject_id
            q_type = data.q_type if "q_type" in fields and data.q_type is not None else target.q_type
            content = data.content if "content" in fields and data.content is not None else target.content
            options = data.options if "options" in fields else target.options
            key = question_dedup.key_from_payload(
                q_type=q_type,
                content=content,
                options=options,
                stimulus_content=await question_dedup.stimulus_content(ctx.db, target.stimulus_id),
            )
            # 只有改动影响查重签名(或换了学科)时才检查,避免改个错别字之外的字段也被拦
            if key.fingerprint != target.dedup_fingerprint or subject_id != target.subject_id:
                await ensure_not_duplicate(
                    ctx,
                    subject_id=subject_id,
                    q_type=q_type,
                    content=content,
                    options=options,
                    stimulus_id=target.stimulus_id,
                    exclude_ids=(target.id,),
                )
        return await crud.question.update_with_tags(
            db=ctx.db, db_obj=target, obj_in=inp.data, user_id=ctx.actor.id
        )


@register
class ReviewQuestion(Capability[QuestionReviewInput, Question]):
    name = "question.review"
    description = "Review a question. Approving increments its review count and publishes it once the subject's required review count is reached; rejecting sends it back to draft."
    input_model = QuestionReviewInput
    authz = Authz.PERMISSION
    permission = Permission.EDIT_QUESTION
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: QuestionReviewInput) -> Question:
        return await _load_visible_question(ctx, inp.id)

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
    description = "Soft-delete a question. Only its creator, a subject manager or a superuser can do this."
    input_model = QuestionIdInput
    authz = Authz.CUSTOM
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: QuestionIdInput) -> Question:
        return await _load_visible_question(ctx, inp.id)

    async def authorize(self, ctx: ExecutionContext, inp: QuestionIdInput, target: Question) -> None:
        if not can_delete_question(target, ctx.actor):
            raise Forbidden("Not enough permissions", ErrorCode.AUTH_FORBIDDEN)

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
    description = "Soft-delete questions in bulk. Questions the user may not delete are skipped instead of failing."
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
            await release_stimulus_slot(ctx.db, question)
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
    description = "Update the source of questions in bulk. Questions not created by the user are skipped."
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
    description = "Confirm or reject draft questions in bulk: confirming moves them to pending review, rejecting soft-deletes them. Questions the user may not change are skipped."
    input_model = schemas.QuestionBatchConfirm
    authz = Authz.CUSTOM
    scope = Scope.SUBJECT
    mutating = True

    async def execute(self, ctx: ExecutionContext, inp: schemas.QuestionBatchConfirm, target: Any) -> dict:
        if inp.action not in ["approve", "reject"]:
            raise Invalid("Invalid action. Must be 'approve' or 'reject'.", ErrorCode.QUESTION_INVALID_REVIEW_ACTION)

        if not inp.question_ids:
            return {"message": "No question IDs provided."}

        questions = await _load_questions_by_ids(ctx, inp.question_ids)
        if not questions:
            raise NotFound("No questions found with provided IDs.", ErrorCode.QUESTION_NONE_FOUND)

        processed_count = 0
        for question in questions:
            if inp.action == "approve":
                allowed = is_question_visible(question, ctx.actor) and permissions.can(
                    ctx.actor, Permission.EDIT_QUESTION, subject_id=question.subject_id
                )
            else:
                allowed = can_delete_question(question, ctx.actor)
            # 只处理草稿，避免误改已入库题目。
            if allowed and question.status == QuestionStatus.DRAFT:
                if inp.action == "approve":
                    question.status = QuestionStatus.PENDING
                elif inp.action == "reject":
                    question.deleted_at = datetime.utcnow()
                    question.updated_by = ctx.actor.id
                    await release_stimulus_slot(ctx.db, question)
                    ctx.db.add(question)
                processed_count += 1

        await ctx.db.commit()
        return {
            "message": f"Successfully {inp.action}d {processed_count} questions.",
            "processed_count": processed_count,
        }
