"""组稿域能力 —— 写路径。

`_resolve_scope`(personal → owner_id 强制为当前用户)留在端点:它是传输层对客户端
输入的收敛;解析结果作为入参传进来。subject 存在性与 scoped 可见性判定属于领域前置条件,
放在各能力的 `load` 里。

鉴权现状:组稿域历史上就没有 Permission 门禁(只要求登录),本期只做搬迁不改行为,
因此全部声明 `Authz.NONE` 并登记在 UNGATED_ALLOWLIST。补门禁需要同时给既有组稿测试
补学科成员关系,另开一期。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app import crud
from app.crud import crud_composition
from app.models.composition import Composition, Folder, ScopeType
from app.schemas.composition import (
    CompositionNodeInput,
    CompositionNodesReplaceResponse,
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
        raise NotFound("Subject not found")


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
        raise NotFound("Folder not found")
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
        raise NotFound("Composition not found")
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
    description = "在指定学科与范围下新建组稿目录。"
    input_model = FolderCreateInput
    authz = Authz.NONE
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
    description = "重命名组稿目录或将其移动到另一个父目录。"
    input_model = FolderUpdateInput
    authz = Authz.NONE
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
    description = "删除组稿目录;目录非空时拒绝。"
    input_model = FolderRefInput
    authz = Authz.NONE
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
    status_value: Optional[str] = None
    folder_id: Optional[int] = None
    folder_id_provided: bool = False
    numbering_enabled: Optional[bool] = None
    scoring_enabled: Optional[bool] = None
    question_display: Optional[Dict[str, bool]] = None


class CompositionReplaceNodesInput(CompositionRevisionInput):
    batch_id: Optional[str] = None
    items: List[CompositionNodeInput]


class CompositionSyncNodesInput(CompositionRevisionInput):
    node_ids: Optional[List[str]] = None


class CompositionFinalizeInput(CompositionRevisionInput):
    label: Optional[str] = None


@register
class CreateComposition(Capability[CompositionCreateInput, Composition]):
    name = "composition.create"
    description = "新建一份稿件(试卷草稿)。"
    input_model = CompositionCreateInput
    authz = Authz.NONE
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
    description = "更新稿件元信息(标题/描述/状态/所在目录/编号与分值开关/题目字段显示)。"
    input_model = CompositionUpdateInput
    authz = Authz.NONE
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
    description = "整份替换稿件的节点树(排版内容)。带乐观锁,revision 不匹配会冲突。"
    input_model = CompositionReplaceNodesInput
    authz = Authz.NONE
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
    description = "把稿件里已过期的题目节点重新同步为题库中的最新内容。"
    input_model = CompositionSyncNodesInput
    authz = Authz.NONE
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
class DeleteComposition(Capability[CompositionRevisionInput, None]):
    name = "composition.delete"
    description = "软删除一份稿件。"
    input_model = CompositionRevisionInput
    authz = Authz.NONE
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
    description = "从回收站恢复一份被软删除的稿件。"
    input_model = CompositionRevisionInput
    authz = Authz.NONE
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: CompositionRevisionInput) -> Composition:
        comp = await _load_scoped_composition(ctx, inp, include_deleted=True)
        if comp.deleted_at is None:
            raise NotFound("Composition not found")
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
    description = "创建一份稿件的副本(节点内容按原样复制,不重新同步题目)。"
    input_model = CompositionRefInput
    authz = Authz.NONE
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
    description = "定稿:冻结当前节点树为一个不可变版本快照。"
    input_model = CompositionFinalizeInput
    authz = Authz.NONE
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
