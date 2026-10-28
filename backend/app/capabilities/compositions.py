"""组稿域能力 —— 写路径。

`_resolve_scope`(personal → owner_id 强制为当前用户)留在端点:它是传输层对客户端
输入的收敛;解析结果作为入参传进来。subject 存在性与 scoped 可见性判定属于领域前置条件,
放在各能力的 `load` 里。

鉴权:组稿写路径统一按学科作用域的 EDIT_QUESTION 判权。personal 稿也不例外 ——
归属某个学科的稿件就应该要求该学科的成员身份,owner_id 只决定可见性不决定权限。
注意 `load` 先于 `authorize`,所以跨学科/跨 scope 仍是 404(不可见),仅已定位到实体
但权限不够时才是 403。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app import crud
from app.core.api_errors import ErrorCode
from app.core.permissions import Permission
from app.crud import crud_composition
from app.models.composition import Composition, CompositionStatus, Folder, ScopeType
from app.schemas.composition import (
    CompositionNodeInput,
    CompositionNodesReplaceResponse,
    CompositionQuestionGroupNodesSyncResponse,
    CompositionQuestionNodesSyncResponse,
)
from app.services import composition_service

from .base import Authz, Capability, Scope
from .context import ExecutionContext
from .errors import NotFound
from .registry import register


class CompositionScopeInput(BaseModel):
    """组稿域一切读写的定位三元组;personal 稿的 owner_id 由调用方强制填当前用户。"""
    subject_id: int
    scope_type: ScopeType
    owner_id: Optional[int] = None


async def _ensure_subject(ctx: ExecutionContext, subject_id: int) -> None:
    if not await crud.subject.get(ctx.db, id=subject_id):
        raise NotFound("Subject not found", ErrorCode.COMPOSITION_SUBJECT_NOT_FOUND)


async def _load_scoped_folder(ctx: ExecutionContext, inp: "FolderRefInput") -> Folder:
    await _ensure_subject(ctx, inp.subject_id)
    folder = await crud_composition.folder.get_scoped(
        ctx.db,
        folder_id=inp.folder_id,
        subject_id=inp.subject_id,
        scope_type=inp.scope_type,
        owner_id=inp.owner_id,
    )
    if folder is None:
        raise NotFound("Folder not found", ErrorCode.COMPOSITION_FOLDER_NOT_FOUND)
    return folder


async def _load_scoped_composition(
    ctx: ExecutionContext,
    inp: "CompositionRefInput",
    *,
    include_deleted: bool = False,
) -> Composition:
    await _ensure_subject(ctx, inp.subject_id)
    comp = await crud_composition.composition.get_scoped(
        ctx.db,
        composition_id=inp.composition_id,
        subject_id=inp.subject_id,
        scope_type=inp.scope_type,
        owner_id=inp.owner_id,
        include_deleted=include_deleted,
    )
    if comp is None:
        raise NotFound("Composition not found", ErrorCode.COMPOSITION_NOT_FOUND)
    return comp


# --------------------------------------------------------------------------- #
# Folder
# --------------------------------------------------------------------------- #
class FolderRefInput(CompositionScopeInput):
    folder_id: int


class FolderCreateInput(CompositionScopeInput):
    name: str
    parent_id: Optional[int] = None


class FolderUpdateInput(FolderRefInput):
    name: Optional[str] = None
    parent_id: Optional[int] = None
    # 「显式传了 parent_id」与「没传」语义不同(前者可移到根目录),必须单独带过来。
    parent_id_provided: bool = False


@register
class CreateFolder(Capability[FolderCreateInput, Folder]):
    name = "composition.create_folder"
    description = "Create a composition folder in the given subject and scope."
    input_model = FolderCreateInput
    authz = Authz.PERMISSION
    permission = Permission.EDIT_QUESTION
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: FolderCreateInput) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(self, ctx: ExecutionContext, inp: FolderCreateInput, target: Any) -> Folder:
        return await composition_service.create_folder(
            ctx.db,
            subject_id=inp.subject_id,
            scope_type=inp.scope_type,
            owner_id=inp.owner_id,
            actor=ctx.actor,
            name=inp.name,
            parent_id=inp.parent_id,
        )


@register
class UpdateFolder(Capability[FolderUpdateInput, Folder]):
    name = "composition.update_folder"
    description = "Rename a composition folder or move it under another parent folder (pass parent_id=null to move it to the root)."
    input_model = FolderUpdateInput
    authz = Authz.PERMISSION
    permission = Permission.EDIT_QUESTION
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: FolderUpdateInput) -> Folder:
        return await _load_scoped_folder(ctx, inp)

    async def execute(self, ctx: ExecutionContext, inp: FolderUpdateInput, target: Folder) -> Folder:
        return await composition_service.update_folder(
            ctx.db,
            folder=target,
            actor=ctx.actor,
            name=inp.name,
            parent_id=inp.parent_id,
            parent_id_provided=inp.parent_id_provided,
        )


@register
class DeleteFolder(Capability[FolderRefInput, None]):
    name = "composition.delete_folder"
    description = "Delete a composition folder. Fails if the folder is not empty."
    input_model = FolderRefInput
    authz = Authz.PERMISSION
    permission = Permission.EDIT_QUESTION
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: FolderRefInput) -> Folder:
        return await _load_scoped_folder(ctx, inp)

    async def execute(self, ctx: ExecutionContext, inp: FolderRefInput, target: Folder) -> None:
        await composition_service.delete_folder(ctx.db, folder=target, actor=ctx.actor)


# --------------------------------------------------------------------------- #
# Composition
# --------------------------------------------------------------------------- #
class CompositionRefInput(CompositionScopeInput):
    composition_id: int


class CompositionRevisionInput(CompositionRefInput):
    expected_revision: int


class CompositionCreateInput(CompositionScopeInput):
    title: str
    description: Optional[str] = None
    folder_id: Optional[int] = None


class CompositionUpdateInput(CompositionRevisionInput):
    title: Optional[str] = None
    description: Optional[str] = None
    status_value: Optional[str] = Field(default=None, description="Composition status: draft or archived.")
    folder_id: Optional[int] = None
    folder_id_provided: bool = False
    numbering_enabled: Optional[bool] = None
    scoring_enabled: Optional[bool] = None
    question_display: Optional[Dict[str, bool]] = None

    @field_validator("status_value")
    @classmethod
    def _check_status(cls, value: Optional[str]) -> Optional[str]:
        # REST 由请求体的枚举把关;MCP 等入口直接构造本入参,这里兜底。
        if value is not None:
            CompositionStatus(value)
        return value


class CompositionReplaceNodesInput(CompositionRevisionInput):
    batch_id: Optional[str] = None
    items: List[CompositionNodeInput]


class CompositionSyncNodesInput(CompositionRevisionInput):
    node_ids: Optional[List[str]] = None


class CompositionSyncQuestionGroupNodesInput(CompositionRevisionInput):
    node_ids: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_node_ids(self) -> "CompositionSyncQuestionGroupNodesInput":
        if not self.node_ids:
            raise ValueError("node_ids must not be empty")
        if len(self.node_ids) != len(set(self.node_ids)):
            raise ValueError("node_ids must be unique")
        return self


class CompositionFinalizeInput(CompositionRevisionInput):
    label: Optional[str] = None


@register
class CreateComposition(Capability[CompositionCreateInput, Composition]):
    name = "composition.create"
    description = "Create a new composition (a draft paper)."
    input_model = CompositionCreateInput
    authz = Authz.PERMISSION
    permission = Permission.EDIT_QUESTION
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: CompositionCreateInput) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(
        self, ctx: ExecutionContext, inp: CompositionCreateInput, target: Any
    ) -> Composition:
        return await composition_service.create_composition(
            ctx.db,
            subject_id=inp.subject_id,
            scope_type=inp.scope_type,
            owner_id=inp.owner_id,
            actor=ctx.actor,
            title=inp.title,
            description=inp.description,
            folder_id=inp.folder_id,
        )


@register
class UpdateComposition(Capability[CompositionUpdateInput, Composition]):
    name = "composition.update"
    description = "Update composition metadata: title, description, status, folder (pass folder_id=null to move it to the root), numbering/scoring switches and question field display. Requires the current revision as expected_revision."
    input_model = CompositionUpdateInput
    authz = Authz.PERMISSION
    permission = Permission.EDIT_QUESTION
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: CompositionUpdateInput) -> Composition:
        return await _load_scoped_composition(ctx, inp)

    async def execute(
        self, ctx: ExecutionContext, inp: CompositionUpdateInput, target: Composition
    ) -> Composition:
        return await composition_service.update_composition(
            ctx.db,
            comp=target,
            actor=ctx.actor,
            expected_revision=inp.expected_revision,
            title=inp.title,
            description=inp.description,
            status_value=inp.status_value,
            folder_id=inp.folder_id,
            folder_id_provided=inp.folder_id_provided,
            numbering_enabled=inp.numbering_enabled,
            scoring_enabled=inp.scoring_enabled,
            question_display=inp.question_display,
        )


@register
class ReplaceCompositionNodes(Capability[CompositionReplaceNodesInput, CompositionNodesReplaceResponse]):
    name = "composition.replace_nodes"
    description = "Replace the whole node tree (layout content) of a composition. Uses optimistic locking: fails with a conflict if expected_revision is stale."
    input_model = CompositionReplaceNodesInput
    authz = Authz.PERMISSION
    permission = Permission.EDIT_QUESTION
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: CompositionReplaceNodesInput) -> Composition:
        return await _load_scoped_composition(ctx, inp)

    async def execute(
        self, ctx: ExecutionContext, inp: CompositionReplaceNodesInput, target: Composition
    ) -> CompositionNodesReplaceResponse:
        revision, nodes = await composition_service.replace_nodes(
            ctx.db,
            comp=target,
            actor=ctx.actor,
            expected_revision=inp.expected_revision,
            batch_id=inp.batch_id,
            items=inp.items,
        )
        return CompositionNodesReplaceResponse(revision=revision, nodes=nodes)


@register
class SyncCompositionQuestionNodes(
    Capability[CompositionSyncNodesInput, CompositionQuestionNodesSyncResponse]
):
    name = "composition.sync_question_nodes"
    description = "Re-sync outdated question nodes in a composition with the latest content from the question bank."
    input_model = CompositionSyncNodesInput
    authz = Authz.PERMISSION
    permission = Permission.EDIT_QUESTION
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: CompositionSyncNodesInput) -> Composition:
        return await _load_scoped_composition(ctx, inp)

    async def execute(
        self, ctx: ExecutionContext, inp: CompositionSyncNodesInput, target: Composition
    ) -> CompositionQuestionNodesSyncResponse:
        revision, nodes = await composition_service.sync_question_nodes(
            ctx.db,
            comp=target,
            actor=ctx.actor,
            expected_revision=inp.expected_revision,
            node_ids=inp.node_ids,
        )
        return CompositionQuestionNodesSyncResponse(revision=revision, nodes=nodes)


@register
class SyncCompositionQuestionGroupNodes(
    Capability[
        CompositionSyncQuestionGroupNodesInput,
        CompositionQuestionGroupNodesSyncResponse,
    ]
):
    name = "composition.sync_question_group_nodes"
    description = "Atomically refresh the frozen snapshots and order of question groups, their materials and all member questions in a composition."
    input_model = CompositionSyncQuestionGroupNodesInput
    authz = Authz.PERMISSION
    permission = Permission.EDIT_QUESTION
    scope = Scope.SUBJECT
    mutating = True

    async def load(
        self, ctx: ExecutionContext, inp: CompositionSyncQuestionGroupNodesInput
    ) -> Composition:
        return await _load_scoped_composition(ctx, inp)

    async def execute(
        self,
        ctx: ExecutionContext,
        inp: CompositionSyncQuestionGroupNodesInput,
        target: Composition,
    ) -> CompositionQuestionGroupNodesSyncResponse:
        revision, nodes = await composition_service.sync_question_group_nodes(
            ctx.db,
            comp=target,
            actor=ctx.actor,
            expected_revision=inp.expected_revision,
            node_ids=inp.node_ids,
        )
        return CompositionQuestionGroupNodesSyncResponse(revision=revision, nodes=nodes)


@register
class DeleteComposition(Capability[CompositionRevisionInput, None]):
    name = "composition.delete"
    description = "Soft-delete a composition (it can be restored later)."
    input_model = CompositionRevisionInput
    authz = Authz.PERMISSION
    permission = Permission.EDIT_QUESTION
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: CompositionRevisionInput) -> Composition:
        return await _load_scoped_composition(ctx, inp)

    async def execute(
        self, ctx: ExecutionContext, inp: CompositionRevisionInput, target: Composition
    ) -> None:
        await composition_service.delete_composition(
            ctx.db, comp=target, actor=ctx.actor, expected_revision=inp.expected_revision
        )


@register
class RestoreComposition(Capability[CompositionRevisionInput, Composition]):
    name = "composition.restore"
    description = "Restore a soft-deleted composition from the trash."
    input_model = CompositionRevisionInput
    authz = Authz.PERMISSION
    permission = Permission.EDIT_QUESTION
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: CompositionRevisionInput) -> Composition:
        comp = await _load_scoped_composition(ctx, inp, include_deleted=True)
        if comp.deleted_at is None:
            raise NotFound("Composition not found", ErrorCode.COMPOSITION_NOT_FOUND)
        return comp

    async def execute(
        self, ctx: ExecutionContext, inp: CompositionRevisionInput, target: Composition
    ) -> Composition:
        return await composition_service.restore_composition(
            ctx.db, comp=target, actor=ctx.actor, expected_revision=inp.expected_revision
        )


@register
class DuplicateComposition(Capability[CompositionRefInput, Composition]):
    name = "composition.duplicate"
    description = "Duplicate a composition. Nodes are copied as-is; questions are not re-synced."
    input_model = CompositionRefInput
    authz = Authz.PERMISSION
    permission = Permission.EDIT_QUESTION
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: CompositionRefInput) -> Composition:
        return await _load_scoped_composition(ctx, inp)

    async def execute(
        self, ctx: ExecutionContext, inp: CompositionRefInput, target: Composition
    ) -> Composition:
        return await composition_service.duplicate_composition(
            ctx.db, source=target, actor=ctx.actor
        )


@register
class FinalizeCompositionVersion(Capability[CompositionFinalizeInput, Any]):
    name = "composition.finalize_version"
    description = "Finalize a composition: freeze the current node tree into an immutable version snapshot."
    input_model = CompositionFinalizeInput
    authz = Authz.PERMISSION
    permission = Permission.EDIT_QUESTION
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: CompositionFinalizeInput) -> Composition:
        # 软删除稿仍可定位(允许查看历史版本);能否新定稿由 service 裁决。
        return await _load_scoped_composition(ctx, inp, include_deleted=True)

    async def execute(
        self, ctx: ExecutionContext, inp: CompositionFinalizeInput, target: Composition
    ) -> Any:
        return await composition_service.finalize_version(
            ctx.db,
            comp=target,
            actor=ctx.actor,
            expected_revision=inp.expected_revision,
            label=inp.label,
        )
