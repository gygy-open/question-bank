// 组稿工作台纯函数：URL/查询构建、目录树、面包屑、scope 校验。
// 这些函数不依赖 Nuxt 运行时，便于聚焦单测。

import type {
  CompositionFolder,
  CompositionFolderNode,
  CompositionScope,
} from '@/types/composition'

export const COMPOSITION_SCOPES: readonly CompositionScope[] = ['shared', 'personal']

export function isCompositionScope(value: unknown): value is CompositionScope {
  return value === 'shared' || value === 'personal'
}

/** 把任意路由参数规整为合法 scope，非法值回退到 shared。 */
export function normalizeScope(value: unknown): CompositionScope {
  return isCompositionScope(value) ? value : 'shared'
}

/** /subjects/{id}/folders 或 /subjects/{id}/compositions 基础路径。 */
export function scopedBasePath(
  subjectId: number,
  resource: 'folders' | 'compositions',
): string {
  return `/subjects/${subjectId}/${resource}`
}

export function folderItemPath(subjectId: number, folderId: number): string {
  return `${scopedBasePath(subjectId, 'folders')}/${folderId}`
}

export function compositionItemPath(subjectId: number, compositionId: number): string {
  return `${scopedBasePath(subjectId, 'compositions')}/${compositionId}`
}

export function compositionRestorePath(subjectId: number, compositionId: number): string {
  return `${compositionItemPath(subjectId, compositionId)}/restore`
}

/** 整棵 AST 节点整体替换路径。 */
export function compositionNodesPath(subjectId: number, compositionId: number): string {
  return `${compositionItemPath(subjectId, compositionId)}/nodes`
}

/** question 节点版本状态路径（只读 stale/deleted 检测，不含题目内容）。 */
export function compositionQuestionRevisionsPath(
  subjectId: number,
  compositionId: number,
): string {
  return `${compositionItemPath(subjectId, compositionId)}/question-revisions`
}

/** question 节点同步路径（刷新冻结快照）。 */
export function compositionQuestionNodesSyncPath(
  subjectId: number,
  compositionId: number,
): string {
  return `${compositionItemPath(subjectId, compositionId)}/question-nodes/sync`
}

/** /subjects/{id}/compositions/{cid}/versions 版本集合路径（定稿/列表）。 */
export function compositionVersionsPath(subjectId: number, compositionId: number): string {
  return `${compositionItemPath(subjectId, compositionId)}/versions`
}

/** 单个版本只读路径（按 version_no）。 */
export function compositionVersionItemPath(
  subjectId: number,
  compositionId: number,
  versionNo: number,
): string {
  return `${compositionVersionsPath(subjectId, compositionId)}/${versionNo}`
}

/** 版本导出路径（DOCX/LaTeX）。 */
export function compositionVersionExportPath(
  subjectId: number,
  compositionId: number,
  versionNo: number,
): string {
  return `${compositionVersionItemPath(subjectId, compositionId, versionNo)}/export`
}

/** /subjects/{id}/compositions/{cid}/events 时间线路径。 */
export function compositionEventsPath(subjectId: number, compositionId: number): string {
  return `${compositionItemPath(subjectId, compositionId)}/events`
}

/** 把顶层过滤器渲染为组稿列表的 query（省略空值）。 */
export function compositionListQuery(params: {
  scope: CompositionScope
  folderId?: number | null
  rootOnly?: boolean
  onlyDeleted?: boolean
  includeDeleted?: boolean
}): Record<string, string | number | boolean> {
  const query: Record<string, string | number | boolean> = { scope: params.scope }
  if (params.folderId != null) query.folder_id = params.folderId
  if (params.rootOnly) query.root_only = true
  if (params.onlyDeleted) query.only_deleted = true
  if (params.includeDeleted) query.include_deleted = true
  return query
}

/** 折叠平铺目录为树；孤儿（父不存在）挂到根。按 name 排序。 */
export function buildFolderTree(folders: CompositionFolder[]): CompositionFolderNode[] {
  const nodes = new Map<number, CompositionFolderNode>()
  for (const f of folders) {
    nodes.set(f.id, { ...f, children: [] })
  }
  const roots: CompositionFolderNode[] = []
  for (const node of nodes.values()) {
    const parent = node.parent_id != null ? nodes.get(node.parent_id) : undefined
    if (parent) parent.children.push(node)
    else roots.push(node)
  }
  const sortRec = (list: CompositionFolderNode[]) => {
    list.sort((a, b) => a.name.localeCompare(b.name))
    list.forEach((n) => sortRec(n.children))
  }
  sortRec(roots)
  return roots
}

/** 从根到指定目录的面包屑路径（含目标自身）。目录不存在时返回空数组。 */
export function folderBreadcrumb(
  folders: CompositionFolder[],
  folderId: number | null,
): CompositionFolder[] {
  if (folderId == null) return []
  const byId = new Map(folders.map((f) => [f.id, f]))
  const chain: CompositionFolder[] = []
  const seen = new Set<number>()
  let current: CompositionFolder | undefined = byId.get(folderId)
  while (current && !seen.has(current.id)) {
    seen.add(current.id)
    chain.unshift(current)
    current = current.parent_id != null ? byId.get(current.parent_id) : undefined
  }
  return chain
}

/** 收集某目录的全部后代 id（不含自身），用于移动时排除非法目标。 */
export function collectDescendantIds(
  folders: CompositionFolder[],
  folderId: number,
): Set<number> {
  const childrenOf = new Map<number, number[]>()
  for (const f of folders) {
    if (f.parent_id != null) {
      const arr = childrenOf.get(f.parent_id) ?? []
      arr.push(f.id)
      childrenOf.set(f.parent_id, arr)
    }
  }
  const out = new Set<number>()
  const stack = [...(childrenOf.get(folderId) ?? [])]
  while (stack.length) {
    const id = stack.pop()!
    if (out.has(id)) continue
    out.add(id)
    stack.push(...(childrenOf.get(id) ?? []))
  }
  return out
}
