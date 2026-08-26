// 组稿编辑态文档模型（CompositionNode AST 阶段）——纯函数，不依赖 Nuxt 运行时。
// 与后端 app/schemas/composition.py + app/services/composition_service.py 契约对齐：
// - 客户端生成节点 UUID（无 temp_id / id_map 往返）。
// - question_details module 的 answer_item 子节点由「规范化」按 scope 派生（镜像服务端
//   _normalize_module_children），重复 question_id 因 question 节点 UUID 不同而各自保留。
// - 序列化整棵 AST 为 PUT .../nodes 载荷；position 不由客户端传入。

import type {
  AnswerFieldKey,
  AnswerItemOverride,
  AnswerItemProps,
  CompositionNode,
  CompositionNodeInput,
  CompositionNodeType,
  CompositionNodesReplaceRequest,
  DetailScope,
  HeadingLevel,
  HeadingProps,
  QuestionContentSnapshot,
  QuestionDetailsProps,
  QuestionRevisionStatus,
} from '@/types/composition'
import { ANSWER_FIELD_KEYS, BODY_SLOT } from '@/types/composition'
import type { Question, RichDocNode, RichNode } from '@/types'
import { isEmptyRichDoc } from '@/components/rich-editor/richDoc'

/** 编辑态节点：id 为客户端生成的稳定 UUID（同时用作渲染 key）。children 仅 module 使用。 */
export interface EditorNode {
  id: string
  nodeType: CompositionNodeType
  content: RichDocNode | null
  props: HeadingProps | QuestionDetailsProps | AnswerItemProps | null
  // question 节点：questionId 引用题库题目；questionRevision/questionContent 由服务端冻结。
  questionId: number | null
  questionRevision: number | null
  questionContent: QuestionContentSnapshot | null
  // module 子节点专用软指针。
  sourceQuestionNodeId: string | null
  anchorBeforeNodeId: string | null
  // question_details module 的规范化子节点序列（answer_item + 自定义 heading/rich_text）。
  children: EditorNode[]
}

/** 编辑态文档：有序的 root 节点。 */
export interface EditorDocument {
  nodes: EditorNode[]
}

// --------------------------------------------------------------------------- //
// UUID / 工厂
// --------------------------------------------------------------------------- //

/** 生成合法 UUID（后端会校验 uuid 格式）；优先 crypto.randomUUID，回退手写 v4。 */
export function generateNodeId(): string {
  const g = globalThis as { crypto?: { randomUUID?: () => string } }
  if (g.crypto?.randomUUID) return g.crypto.randomUUID()
  // RFC 4122 v4 回退。
  const hex = '0123456789abcdef'
  let out = ''
  for (let i = 0; i < 36; i += 1) {
    if (i === 8 || i === 13 || i === 18 || i === 23) out += '-'
    else if (i === 14) out += '4'
    else if (i === 19) out += hex[(Math.floor(Math.random() * 4) + 8)]
    else out += hex[Math.floor(Math.random() * 16)]
  }
  return out
}

function emptyParagraphDoc(): RichDocNode {
  return { type: 'doc', content: [{ type: 'paragraph' }] }
}

function baseNode(nodeType: CompositionNodeType): EditorNode {
  return {
    id: generateNodeId(),
    nodeType,
    content: null,
    props: null,
    questionId: null,
    questionRevision: null,
    questionContent: null,
    sourceQuestionNodeId: null,
    anchorBeforeNodeId: null,
    children: [],
  }
}

export function createRichTextNode(): EditorNode {
  const node = baseNode('rich_text')
  node.content = emptyParagraphDoc()
  return node
}

export function createHeadingNode(level: HeadingLevel = 2): EditorNode {
  const node = baseNode('heading')
  node.content = emptyParagraphDoc()
  node.props = { level }
  return node
}

export function createPageBreakNode(): EditorNode {
  return baseNode('page_break')
}

/** 把实时题目冻结为 question 节点的内容快照（不含 id/revision，与后端 QuestionContentSnapshot 对齐）。 */
export function questionContentSnapshotFromQuestion(q: Question): QuestionContentSnapshot {
  return {
    content_schema_version: q.content_schema_version,
    q_type: q.q_type,
    content: q.content ?? null,
    options: q.options ?? null,
    answer: q.answer ?? null,
    thinking: q.thinking ?? null,
    analysis: q.analysis ?? null,
    summary: q.summary ?? null,
    difficulty: q.difficulty,
    source: q.source ?? null,
  }
}

export function createQuestionNode(question: Question): EditorNode {
  const node = baseNode('question')
  node.questionId = question.id
  node.questionRevision = question.content_revision
  node.questionContent = questionContentSnapshotFromQuestion(question)
  return node
}

function defaultDetailFields(): Record<AnswerFieldKey, boolean> {
  return { answer: true, thinking: false, analysis: false, summary: false }
}

/** 新建 question_details module（子节点由规范化派生）。 */
export function createQuestionDetailsModule(
  scope: DetailScope = 'all',
  fields: Record<AnswerFieldKey, boolean> = defaultDetailFields(),
): EditorNode {
  const node = baseNode('question_details')
  node.props = { scope, fields: { ...fields } }
  return node
}

/** 汇总模块预设：参考答案（仅答案）与答案解析（答案 + 解析）。 */
export const DETAIL_PRESETS = {
  reference: (scope: DetailScope = 'all'): EditorNode => {
    const moduleNode = createQuestionDetailsModule(scope, {
      answer: true,
      thinking: false,
      analysis: false,
      summary: false,
    })
    const heading = createHeadingNode(2)
    heading.content = headingTextToDoc('参考答案')
    moduleNode.children = [heading]
    return moduleNode
  },
  analysis: (scope: DetailScope = 'all'): EditorNode => {
    const moduleNode = createQuestionDetailsModule(scope, {
      answer: true,
      thinking: false,
      analysis: true,
      summary: false,
    })
    const heading = createHeadingNode(2)
    heading.content = headingTextToDoc('答案与解析')
    moduleNode.children = [heading]
    return moduleNode
  },
} as const

function defaultAnswerItemOverrides(): Record<AnswerFieldKey, AnswerItemOverride> {
  return { answer: null, thinking: null, analysis: null, summary: null }
}

export function defaultAnswerItemProps(): AnswerItemProps {
  return { included: true, overrides: defaultAnswerItemOverrides() }
}

/** 新建挂在 module 内、锚定在某 answer_item 之前的自定义 heading/rich_text 子节点。 */
export function createModuleCustomNode(
  nodeType: 'heading' | 'rich_text',
  anchorBeforeNodeId: string | null,
): EditorNode {
  const node = nodeType === 'heading' ? createHeadingNode() : createRichTextNode()
  node.anchorBeforeNodeId = anchorBeforeNodeId
  return node
}

// --------------------------------------------------------------------------- //
// 类型化 props 访问器
// --------------------------------------------------------------------------- //

export function headingLevelOf(node: EditorNode): HeadingLevel {
  return (node.props as HeadingProps | null)?.level ?? 2
}

export function detailPropsOf(node: EditorNode): QuestionDetailsProps {
  return (node.props as QuestionDetailsProps | null) ?? { scope: 'all', fields: defaultDetailFields() }
}

export function answerItemPropsOf(node: EditorNode): AnswerItemProps {
  return (node.props as AnswerItemProps | null) ?? defaultAnswerItemProps()
}

// --------------------------------------------------------------------------- //
// 服务端 nodes ⇄ 编辑态文档
// --------------------------------------------------------------------------- //

/** 由服务端返回的扁平 CompositionNode[] 构造编辑态文档（root 树 + module 子树）。 */
export function documentFromNodes(nodes: CompositionNode[]): EditorDocument {
  const byId = new Map<string, EditorNode>()
  const childrenByParent = new Map<string, CompositionNode[]>()
  const roots: CompositionNode[] = []

  for (const n of nodes) {
    if (n.parent_id == null) {
      roots.push(n)
    } else {
      const arr = childrenByParent.get(n.parent_id) ?? []
      arr.push(n)
      childrenByParent.set(n.parent_id, arr)
    }
  }

  const toEditor = (n: CompositionNode): EditorNode => {
    const node = baseNode(n.node_type)
    node.id = n.id
    node.props = (n.props as EditorNode['props']) ?? null
    if (n.node_type === 'question') {
      node.questionId = n.question_id
      node.questionRevision = n.question_revision
      node.questionContent = (n.content as QuestionContentSnapshot | null) ?? null
    } else if (n.node_type === 'answer_item') {
      node.sourceQuestionNodeId = n.source_question_node_id
    } else {
      node.content = (n.content as RichDocNode | null) ?? null
      node.anchorBeforeNodeId = n.anchor_before_node_id ?? null
    }
    byId.set(node.id, node)
    return node
  }

  const orderByPosition = (list: CompositionNode[]) =>
    [...list].sort((a, b) => a.position - b.position || a.id.localeCompare(b.id))

  const rootNodes = orderByPosition(roots).map((n) => {
    const editor = toEditor(n)
    if (n.node_type === 'question_details') {
      editor.children = orderByPosition(childrenByParent.get(n.id) ?? []).map(toEditor)
    }
    return editor
  })

  return { nodes: rootNodes }
}

// --------------------------------------------------------------------------- //
// 规范化：镜像服务端 _normalize_module_children
// --------------------------------------------------------------------------- //

function rootQuestionNodes(doc: EditorDocument): EditorNode[] {
  return doc.nodes.filter((n) => n.nodeType === 'question')
}

/**
 * 按 module scope 规范化单个 module 的子节点序列（不修改入参）。
 * - scope=all → 整稿全部 root question 节点；before → module 之前的 root question 节点。
 * - 每个范围内 question 节点产出一条 answer_item（按 question 节点 UUID 归属，重复 question_id 各自保留）。
 * - 尽量复用现有 answer_item（按 sourceQuestionNodeId 顺序消费）以保留 id / included / overrides。
 * - 自定义 heading/rich_text 按 anchorBeforeNodeId 混排，悬空锚点落到末尾（保序）。
 */
function normalizeSingleModule(
  moduleNode: EditorNode,
  scopedQuestions: EditorNode[],
): EditorNode[] {
  const clientBySource = new Map<string, EditorNode[]>()
  for (const child of moduleNode.children) {
    if (child.nodeType === 'answer_item' && child.sourceQuestionNodeId) {
      const arr = clientBySource.get(child.sourceQuestionNodeId) ?? []
      arr.push(child)
      clientBySource.set(child.sourceQuestionNodeId, arr)
    }
  }

  const answerItems: EditorNode[] = scopedQuestions.map((q) => {
    const pool = clientBySource.get(q.id)
    const reused = pool && pool.length ? pool.shift() : undefined
    if (reused) {
      return {
        ...reused,
        sourceQuestionNodeId: q.id,
        props: reused.props ?? defaultAnswerItemProps(),
        anchorBeforeNodeId: null,
        children: [],
      }
    }
    const fresh = baseNode('answer_item')
    fresh.sourceQuestionNodeId = q.id
    fresh.props = defaultAnswerItemProps()
    return fresh
  })

  const finalIds = new Set(answerItems.map((ai) => ai.id))
  const anchored = new Map<string, EditorNode[]>()
  const trailing: EditorNode[] = []
  for (const child of moduleNode.children) {
    if (child.nodeType !== 'heading' && child.nodeType !== 'rich_text') continue
    if (child.anchorBeforeNodeId && finalIds.has(child.anchorBeforeNodeId)) {
      const arr = anchored.get(child.anchorBeforeNodeId) ?? []
      arr.push(child)
      anchored.set(child.anchorBeforeNodeId, arr)
    } else {
      trailing.push({ ...child, anchorBeforeNodeId: null })
    }
  }

  const ordered: EditorNode[] = []
  for (const ai of answerItems) {
    for (const custom of anchored.get(ai.id) ?? []) ordered.push(custom)
    ordered.push(ai)
  }
  ordered.push(...trailing)
  return ordered
}

/** 规范化整篇文档的所有 module 子节点，返回新文档（不改入参）。 */
export function normalizeDocument(doc: EditorDocument): EditorDocument {
  const questions = rootQuestionNodes(doc)
  const questionIndex = new Map<string, number>()
  doc.nodes.forEach((n, i) => questionIndex.set(n.id, i))

  const nodes = doc.nodes.map((node) => {
    if (node.nodeType !== 'question_details') return node
    const props = detailPropsOf(node)
    const moduleIdx = questionIndex.get(node.id) ?? doc.nodes.length
    const scoped =
      props.scope === 'all'
        ? questions
        : questions.filter((q) => (questionIndex.get(q.id) ?? 0) < moduleIdx)
    return { ...node, children: normalizeSingleModule(node, scoped) }
  })

  return { nodes }
}

// --------------------------------------------------------------------------- //
// 序列化为 PUT .../nodes 载荷
// --------------------------------------------------------------------------- //

function nodeToInput(node: EditorNode, parentId: string | null): CompositionNodeInput {
  const slot = parentId == null ? undefined : BODY_SLOT
  switch (node.nodeType) {
    case 'rich_text':
      return { id: node.id, parent_id: parentId, slot, node_kind: 'block', node_type: 'rich_text', content: node.content, ...(node.anchorBeforeNodeId ? { anchor_before_node_id: node.anchorBeforeNodeId } : {}) }
    case 'heading':
      return { id: node.id, parent_id: parentId, slot, node_kind: 'block', node_type: 'heading', content: node.content, props: { level: headingLevelOf(node) }, ...(node.anchorBeforeNodeId ? { anchor_before_node_id: node.anchorBeforeNodeId } : {}) }
    case 'question':
      return { id: node.id, node_kind: 'block', node_type: 'question', question_id: node.questionId }
    case 'page_break':
      return { id: node.id, node_kind: 'block', node_type: 'page_break' }
    case 'question_details': {
      const props = detailPropsOf(node)
      return { id: node.id, node_kind: 'module', node_type: 'question_details', props: { scope: props.scope, fields: { ...props.fields } } }
    }
    case 'answer_item': {
      const props = answerItemPropsOf(node)
      return { id: node.id, parent_id: parentId, slot, node_kind: 'reference', node_type: 'answer_item', source_question_node_id: node.sourceQuestionNodeId, props: { included: props.included, overrides: { ...props.overrides } } }
    }
  }
}

/** 序列化整棵 AST：先规范化，再 root 先、module 子后展平为 nodes 数组。 */
export function documentToReplaceRequest(
  doc: EditorDocument,
  expectedRevision: number,
  batchId?: string,
): CompositionNodesReplaceRequest {
  const normalized = normalizeDocument(doc)
  const nodes: CompositionNodeInput[] = []
  for (const root of normalized.nodes) {
    nodes.push(nodeToInput(root, null))
    if (root.nodeType === 'question_details') {
      for (const child of root.children) nodes.push(nodeToInput(child, root.id))
    }
  }
  const payload: CompositionNodesReplaceRequest = { expected_revision: expectedRevision, nodes }
  if (batchId) payload.batch_id = batchId
  return payload
}

// --------------------------------------------------------------------------- //
// root 层 / module 子层编辑操作（均返回新文档，不改入参）
// --------------------------------------------------------------------------- //

export function insertRootNodeAfter(
  doc: EditorDocument,
  index: number,
  node: EditorNode,
): EditorDocument {
  const next = doc.nodes.slice()
  const at = index < 0 ? 0 : Math.min(index + 1, next.length)
  next.splice(at, 0, node)
  return normalizeDocument({ nodes: next })
}

export function moveRootNode(
  doc: EditorDocument,
  index: number,
  direction: 'up' | 'down',
): EditorDocument {
  const target = direction === 'up' ? index - 1 : index + 1
  if (index < 0 || index >= doc.nodes.length || target < 0 || target >= doc.nodes.length) {
    return { nodes: doc.nodes.slice() }
  }
  const next = doc.nodes.slice()
  const tmp = next[index]!
  next[index] = next[target]!
  next[target] = tmp
  return normalizeDocument({ nodes: next })
}

export function removeRootNode(doc: EditorDocument, id: string): EditorDocument {
  return normalizeDocument({ nodes: doc.nodes.filter((n) => n.id !== id) })
}

/** 用 patch 更新某个（root 或 module 子）节点。 */
export function patchNode(
  doc: EditorDocument,
  id: string,
  patch: Partial<Pick<EditorNode, 'content' | 'props'>>,
): EditorDocument {
  const apply = (n: EditorNode): EditorNode => {
    if (n.id !== id) return n
    return {
      ...n,
      ...('content' in patch ? { content: patch.content ?? null } : {}),
      ...('props' in patch ? { props: patch.props ?? null } : {}),
    }
  }
  const nodes = doc.nodes.map((root) => {
    const updated = apply(root)
    if (root.nodeType === 'question_details') {
      return { ...updated, children: root.children.map(apply) }
    }
    return updated
  })
  return { nodes }
}

/** 在 module 内某 answer_item 之前插入自定义 heading/rich_text 子节点。 */
export function insertModuleCustomBefore(
  doc: EditorDocument,
  moduleId: string,
  answerItemId: string | null,
  node: EditorNode,
): EditorDocument {
  const nodes = doc.nodes.map((root) => {
    if (root.id !== moduleId || root.nodeType !== 'question_details') return root
    const children = root.children.slice()
    const idx = answerItemId == null ? -1 : children.findIndex((c) => c.id === answerItemId)
    const custom = { ...node, anchorBeforeNodeId: answerItemId }
    if (idx < 0) children.push(custom)
    else children.splice(idx, 0, custom)
    return { ...root, children }
  })
  return normalizeDocument({ nodes })
}

/** 移动 module 内某个自定义子节点（仅在自定义子节点之间换位；answer_item 不可重排）。 */
export function moveModuleCustomChild(
  doc: EditorDocument,
  moduleId: string,
  childId: string,
  direction: 'up' | 'down',
): EditorDocument {
  const nodes = doc.nodes.map((root) => {
    if (root.id !== moduleId || root.nodeType !== 'question_details') return root
    const children = root.children.slice()
    const idx = children.findIndex((c) => c.id === childId)
    if (idx < 0) return root
    const child = children[idx]!
    if (child.nodeType === 'answer_item') return root
    // 目标：跨过相邻的 answer_item，落到相邻的自定义可放置点。
    const target = direction === 'up' ? idx - 1 : idx + 1
    if (target < 0 || target >= children.length) return root
    // 重新锚定：move up → 锚到目标位置对应的 answer_item；到末尾则清锚。
    children.splice(idx, 1)
    children.splice(target, 0, child)
    return reanchorModuleCustom({ ...root, children })
  })
  return normalizeDocument({ nodes })
}

/** 删除 module 内某个自定义子节点。 */
export function removeModuleCustomChild(
  doc: EditorDocument,
  moduleId: string,
  childId: string,
): EditorDocument {
  const nodes = doc.nodes.map((root) => {
    if (root.id !== moduleId || root.nodeType !== 'question_details') return root
    return { ...root, children: root.children.filter((c) => c.id !== childId) }
  })
  return normalizeDocument({ nodes })
}

/** 依据当前子节点顺序，把每个自定义节点的 anchor 重设为其后紧邻的 answer_item（无则清锚）。 */
function reanchorModuleCustom(moduleNode: EditorNode): EditorNode {
  const children = moduleNode.children.map((c) => ({ ...c }))
  for (let i = 0; i < children.length; i += 1) {
    const c = children[i]!
    if (c.nodeType !== 'heading' && c.nodeType !== 'rich_text') continue
    let anchor: string | null = null
    for (let j = i + 1; j < children.length; j += 1) {
      if (children[j]!.nodeType === 'answer_item') {
        anchor = children[j]!.id
        break
      }
    }
    c.anchorBeforeNodeId = anchor
  }
  return { ...moduleNode, children }
}

// --------------------------------------------------------------------------- //
// 脏检测 / 保存前校验 / 版本状态
// --------------------------------------------------------------------------- //

function snapNode(node: EditorNode): Record<string, unknown> {
  const base: Record<string, unknown> = { t: node.nodeType }
  switch (node.nodeType) {
    case 'rich_text':
      base.c = node.content
      break
    case 'heading':
      base.c = node.content
      base.p = { level: headingLevelOf(node) }
      break
    case 'question':
      // 忽略 questionRevision / questionContent（服务端钉住，同步时才变）。
      base.q = node.questionId
      break
    case 'question_details': {
      const props = detailPropsOf(node)
      base.p = { scope: props.scope, fields: props.fields }
      base.children = node.children.map(snapNode)
      break
    }
    case 'answer_item': {
      const props = answerItemPropsOf(node)
      base.src = node.sourceQuestionNodeId
      base.p = { included: props.included, overrides: props.overrides }
      break
    }
    case 'page_break':
      break
  }
  return base
}

/** 脏检测快照：先规范化，忽略节点 id / questionRevision / questionContent。 */
export function snapshotDocument(doc: EditorDocument): string {
  const normalized = normalizeDocument(doc)
  return JSON.stringify(normalized.nodes.map(snapNode))
}

/** 保存前的阻断性问题：空文本/空标题、缺题引用。返回人类可读描述列表。 */
export function collectDocumentIssues(doc: EditorDocument): string[] {
  const issues: string[] = []
  doc.nodes.forEach((node, i) => {
    const at = `第 ${i + 1} 个块`
    if (node.nodeType === 'rich_text' && isEmptyRichDoc(node.content)) {
      issues.push(`${at}（文本）内容为空`)
    } else if (node.nodeType === 'heading' && isEmptyRichDoc(node.content)) {
      issues.push(`${at}（标题）内容为空`)
    } else if (node.nodeType === 'question' && node.questionId == null) {
      issues.push(`${at}（题目）未选择题目`)
    } else if (node.nodeType === 'question_details') {
      node.children.forEach((child) => {
        if (child.nodeType === 'rich_text' && isEmptyRichDoc(child.content)) {
          issues.push(`${at}（汇总模块内文本）内容为空`)
        } else if (child.nodeType === 'heading' && isEmptyRichDoc(child.content)) {
          issues.push(`${at}（汇总模块内标题）内容为空`)
        }
      })
    }
  })
  return issues
}

/** 单个 question 节点相对实时题库的状态：stale（题库有更新）/ deleted（题库已删除）。 */
export function questionNodeStatus(
  node: EditorNode,
  status: QuestionRevisionStatus | null | undefined,
): { stale: boolean; deleted: boolean } {
  if (node.nodeType !== 'question' || node.questionId == null || !status) {
    return { stale: false, deleted: false }
  }
  if (!status.available) return { stale: false, deleted: true }
  const stale =
    node.questionRevision != null &&
    status.current_revision != null &&
    status.current_revision > node.questionRevision
  return { stale, deleted: false }
}

/** 收集全部过期（stale）question 节点的 UUID（“同步全部”用）。 */
export function collectStaleQuestionNodeIds(
  doc: EditorDocument,
  statusMap: Map<number, QuestionRevisionStatus>,
): string[] {
  const ids: string[] = []
  for (const node of doc.nodes) {
    if (node.nodeType !== 'question' || node.questionId == null) continue
    if (questionNodeStatus(node, statusMap.get(node.questionId)).stale) ids.push(node.id)
  }
  return ids
}

// --------------------------------------------------------------------------- //
// heading 富文本 <-> 纯文本（首期 heading 用受限单行编辑）
// --------------------------------------------------------------------------- //

export function headingDocToText(doc: RichDocNode | null | undefined): string {
  if (!doc || doc.type !== 'doc') return ''
  const first = (doc.content ?? [])[0]
  if (!first || first.type !== 'paragraph') return ''
  const parts: string[] = []
  for (const node of first.content ?? []) {
    if (node.type === 'text' && node.text) parts.push(node.text)
  }
  return parts.join('')
}

export function headingTextToDoc(text: string): RichDocNode {
  if (!text) return emptyParagraphDoc()
  return { type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text }] }] }
}

export function headingHasRichInline(doc: RichDocNode | null | undefined): boolean {
  if (!doc || doc.type !== 'doc') return false
  const first = (doc.content ?? [])[0]
  if (!first || first.type !== 'paragraph') return false
  return (first.content ?? []).some((node: RichNode) => node.type !== 'text')
}
