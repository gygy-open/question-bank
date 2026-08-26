import type {
  Composition,
  CompositionCreatePayload,
  CompositionNodesReplaceRequest,
  CompositionNodesReplaceResponse,
  CompositionDetail,
  CompositionFolder,
  CompositionMetaUpdatePayload,
  CompositionQuestionNodesSyncRequest,
  CompositionQuestionNodesSyncResponse,
  CompositionScope,
  CompositionVersionCreatePayload,
  CompositionVersionDetail,
  CompositionVersionSummary,
  FolderCreatePayload,
  FolderUpdatePayload,
  QuestionRevisionStatus,
} from '@/types/composition'
import {
  compositionNodesPath,
  compositionItemPath,
  compositionListQuery,
  compositionQuestionNodesSyncPath,
  compositionQuestionRevisionsPath,
  compositionRestorePath,
  compositionVersionItemPath,
  compositionVersionsPath,
  folderItemPath,
  scopedBasePath,
} from '@/lib/compositions'

/**
 * 409 冲突的可识别错误：
 * - kind='revision'：乐观锁失败（组稿被他人改动），detail 含 "revision mismatch"
 * - kind='folder-not-empty'：删除非空目录
 * - kind='other'：其它 409
 */
export class CompositionConflictError extends Error {
  readonly status = 409
  readonly kind: 'revision' | 'folder-not-empty' | 'other'
  readonly detail: string

  constructor(detail: string) {
    super(detail || 'conflict')
    this.name = 'CompositionConflictError'
    this.detail = detail
    if (/revision/i.test(detail)) this.kind = 'revision'
    else if (/not empty/i.test(detail)) this.kind = 'folder-not-empty'
    else this.kind = 'other'
  }
}

function extractStatus(err: unknown): number | undefined {
  const e = err as { status?: number; statusCode?: number; response?: { status?: number } }
  return e?.status ?? e?.statusCode ?? e?.response?.status
}

function extractDetail(err: unknown): string {
  const e = err as {
    data?: { detail?: string }
    response?: { _data?: { detail?: string } }
  }
  return e?.data?.detail ?? e?.response?._data?.detail ?? ''
}

function mapConflict(err: unknown): never {
  if (extractStatus(err) === 409) {
    throw new CompositionConflictError(extractDetail(err))
  }
  throw err
}

/**
 * 组稿工作台数据层：封装 folder / composition 的 CRUD 与软删除/恢复。
 * scope 决定共享/个人；subject_id 来自全局科目上下文，由调用方传入当前科目。
 * personal owner_id 永远由后端依据鉴权注入，前端不构造、不传递。
 */
export function useCompositions() {
  const { $api } = useNuxtApp()

  // ---------------------------------------------------------------- Folders //
  const listFolders = (subjectId: number, scope: CompositionScope) =>
    $api<CompositionFolder[]>(scopedBasePath(subjectId, 'folders'), {
      query: { scope },
    })

  const createFolder = (
    subjectId: number,
    scope: CompositionScope,
    payload: FolderCreatePayload,
  ) =>
    $api<CompositionFolder>(scopedBasePath(subjectId, 'folders'), {
      method: 'POST',
      query: { scope },
      body: payload,
    }).catch(mapConflict)

  const updateFolder = (
    subjectId: number,
    scope: CompositionScope,
    folderId: number,
    payload: FolderUpdatePayload,
  ) =>
    $api<CompositionFolder>(folderItemPath(subjectId, folderId), {
      method: 'PATCH',
      query: { scope },
      body: payload,
    }).catch(mapConflict)

  const deleteFolder = (
    subjectId: number,
    scope: CompositionScope,
    folderId: number,
  ) =>
    $api(folderItemPath(subjectId, folderId), {
      method: 'DELETE',
      query: { scope },
    }).catch(mapConflict)

  // ----------------------------------------------------------- Compositions //
  const listCompositions = (
    subjectId: number,
    scope: CompositionScope,
    opts: {
      folderId?: number | null
      rootOnly?: boolean
      onlyDeleted?: boolean
      includeDeleted?: boolean
    } = {},
  ) =>
    $api<Composition[]>(scopedBasePath(subjectId, 'compositions'), {
      query: compositionListQuery({ scope, ...opts }),
    })

  const getComposition = (
    subjectId: number,
    scope: CompositionScope,
    compositionId: number,
    opts: { includeDeleted?: boolean } = {},
  ) =>
    $api<CompositionDetail>(compositionItemPath(subjectId, compositionId), {
      query: opts.includeDeleted ? { scope, include_deleted: true } : { scope },
    })

  const createComposition = (
    subjectId: number,
    scope: CompositionScope,
    payload: CompositionCreatePayload,
  ) =>
    $api<Composition>(scopedBasePath(subjectId, 'compositions'), {
      method: 'POST',
      query: { scope },
      body: payload,
    }).catch(mapConflict)

  const updateComposition = (
    subjectId: number,
    scope: CompositionScope,
    compositionId: number,
    payload: CompositionMetaUpdatePayload,
  ) =>
    $api<Composition>(compositionItemPath(subjectId, compositionId), {
      method: 'PATCH',
      query: { scope },
      body: payload,
    }).catch(mapConflict)

  const deleteComposition = (
    subjectId: number,
    scope: CompositionScope,
    compositionId: number,
    expectedRevision: number,
  ) =>
    $api(compositionItemPath(subjectId, compositionId), {
      method: 'DELETE',
      query: { scope, expected_revision: expectedRevision },
    }).catch(mapConflict)

  const restoreComposition = (
    subjectId: number,
    scope: CompositionScope,
    compositionId: number,
    expectedRevision: number,
  ) =>
    $api<Composition>(compositionRestorePath(subjectId, compositionId), {
      method: 'POST',
      query: { scope, expected_revision: expectedRevision },
    }).catch(mapConflict)

  // 画布：整棵 AST 节点整体替换。乐观锁经 expected_revision；409 复用冲突映射。
  const replaceNodes = (
    subjectId: number,
    scope: CompositionScope,
    compositionId: number,
    payload: CompositionNodesReplaceRequest,
  ) =>
    $api<CompositionNodesReplaceResponse>(
      compositionNodesPath(subjectId, compositionId),
      {
        method: 'PUT',
        query: { scope },
        body: payload,
      },
    ).catch(mapConflict)

  // 题目版本状态：批量返回稿件内每 question_id 的当前 revision 与可用性（不含题目内容）。
  const getQuestionRevisions = (
    subjectId: number,
    scope: CompositionScope,
    compositionId: number,
  ) =>
    $api<QuestionRevisionStatus[]>(
      compositionQuestionRevisionsPath(subjectId, compositionId),
      { query: { scope } },
    )

  // 同步 question 节点：刷新冻结快照并立即落库。乐观锁经 expected_revision；409 复用冲突映射。
  const syncQuestionNodes = (
    subjectId: number,
    scope: CompositionScope,
    compositionId: number,
    payload: CompositionQuestionNodesSyncRequest,
  ) =>
    $api<CompositionQuestionNodesSyncResponse>(
      compositionQuestionNodesSyncPath(subjectId, compositionId),
      {
        method: 'POST',
        query: { scope },
        body: payload,
      },
    ).catch(mapConflict)

  // ------------------------------------------------------------- Versions //
  // 定稿：冻结当前 revision 为不可变版本。不修改 composition.revision；409 复用冲突映射。
  const finalizeVersion = (
    subjectId: number,
    scope: CompositionScope,
    compositionId: number,
    payload: CompositionVersionCreatePayload,
  ) =>
    $api<CompositionVersionDetail>(
      compositionVersionsPath(subjectId, compositionId),
      {
        method: 'POST',
        query: { scope },
        body: payload,
      },
    ).catch(mapConflict)

  // 版本列表：不含 snapshot，按 version_no 排列。
  const listVersions = (
    subjectId: number,
    scope: CompositionScope,
    compositionId: number,
  ) =>
    $api<CompositionVersionSummary[]>(
      compositionVersionsPath(subjectId, compositionId),
      { query: { scope } },
    )

  // 单版本只读 detail：含不可变 snapshot。
  const getVersion = (
    subjectId: number,
    scope: CompositionScope,
    compositionId: number,
    versionNo: number,
  ) =>
    $api<CompositionVersionDetail>(
      compositionVersionItemPath(subjectId, compositionId, versionNo),
      { query: { scope } },
    )

  return {
    listFolders,
    createFolder,
    updateFolder,
    deleteFolder,
    listCompositions,
    getComposition,
    createComposition,
    updateComposition,
    deleteComposition,
    restoreComposition,
    replaceNodes,
    getQuestionRevisions,
    syncQuestionNodes,
    finalizeVersion,
    listVersions,
    getVersion,
  }
}
