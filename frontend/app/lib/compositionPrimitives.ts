// AI 增量编辑原语 —— 把模型给的一批操作应用到编辑态文档上。
//
// 为什么在前端：AST 代数（插入/删除/移动/规范化）只有 compositionDocument.ts 这一份实现，
// 后端只保留「全量替换 + 校验」这一个持久化边界；而且只有这里手里有用户未保存的在编文档。
//
// 入参已由后端 composition_ops.py 校验并归一过（rich_text 的 Markdown 在那边就转成了
// RichDoc —— 转换器含公式与表格，前端再实现一份必然漂移）。这里只做纯结构操作。
//
// 语义：**部分成功**。某条操作失败不影响其余操作，逐条回报给模型让它自己补救；
// 系统拥有的字段（节点 id / question 冻结快照 / 软指针）一律不接受模型写入。

import type {
  AnswerFieldKey,
  AnswerSpaceStyle,
  DetailScope,
  HeadingLevel,
  HeadingProps,
  QuestionDetailsProps,
} from '@/types/composition'
import { ANSWER_FIELD_KEYS } from '@/types/composition'
import type { Question, RichDocNode } from '@/types'
import type { EditorDocument, EditorNode } from '@/lib/compositionDocument'
import {
  answerSpacePropsOf,
  createAnswerSpaceNode,
  createHeadingNode,
  createPageBreakNode,
  createQuestionDetailsModule,
  createQuestionNode,
  createRichTextNode,
  detailPropsOf,
  headingTextToDoc,
  insertRootNodesAfter,
  normalizeDocument,
  patchNode,
  questionPropsWithNumber,
  questionPropsWithScore,
  questionPropsWithShow,
} from '@/lib/compositionDocument'

export type ShowValue = 'show' | 'hide' | 'inherit'

export type AiInsertNode =
  | { type: 'rich_text'; rich_doc_blocks: RichDocNode[] }
  | { type: 'heading'; text: string; level: HeadingLevel }
  | { type: 'question'; question_id: number; number?: string; score?: number }
  | { type: 'page_break' }
  | { type: 'answer_space'; lines: number; style: AnswerSpaceStyle }

export type AiOperation =
  | { op: 'insert_nodes'; after: string; nodes: AiInsertNode[] }
  | { op: 'remove_nodes'; node_ids: string[] }
  | { op: 'move_node'; node_id: string; before: string | null }
  | { op: 'set_node_props'; node_id: string; props: Record<string, unknown>; clear: string[] }
  | { op: 'show_question_fields'; node_id: string; show: Partial<Record<AnswerFieldKey, ShowValue>> }
  | {
      op: 'add_details_module'
      after: string
      scope: DetailScope
      fields: Record<AnswerFieldKey, boolean>
      title: string
    }

export interface OperationResult {
  op: string
  ok: boolean
  message: string
}

export interface ApplyDeps {
  /** 取实时题目用于构造 question 节点的冻结快照；绝不能用缓存的展示数据。 */
  loadQuestions: (ids: number[]) => Promise<Question[]>
}

export interface ApplyOutcome {
  doc: EditorDocument
  results: OperationResult[]
}

// 每类节点允许被 set_node_props 改写的属性。
const SETTABLE_BY_TYPE: Partial<Record<EditorNode['nodeType'], string[]>> = {
  question: ['number', 'score'],
  heading: ['level'],
  answer_space: ['lines', 'style'],
  question_details: ['scope', 'fields'],
}

const ANCHOR_START = 'start'
const ANCHOR_END = 'end'

function rootIndexOf(doc: EditorDocument, id: string): number {
  return doc.nodes.findIndex((n) => n.id === id)
}

function isModuleChild(doc: EditorDocument, id: string): boolean {
  return doc.nodes.some((n) => n.children.some((c) => c.id === id))
}

/** 定位插入锚点，返回「插到第几个 root 之后」；-1 表示插到最前。 */
function resolveAnchor(doc: EditorDocument, after: string): number {
  if (after === ANCHOR_START) return -1
  if (after === ANCHOR_END) return doc.nodes.length - 1
  const idx = rootIndexOf(doc, after)
  if (idx < 0) throw new Error(`找不到节点 ${after}，请先用 read_composition_outline 获取最新的节点 id。`)
  return idx
}

function requireRootNode(doc: EditorDocument, id: string): EditorNode {
  const idx = rootIndexOf(doc, id)
  if (idx >= 0) return doc.nodes[idx]!
  if (isModuleChild(doc, id)) {
    throw new Error(`节点 ${id} 是参考答案模块内的子节点，不支持直接修改；请改动模块本身或它引用的题目。`)
  }
  throw new Error(`找不到节点 ${id}，请先用 read_composition_outline 获取最新的节点 id。`)
}

function buildInsertNode(spec: AiInsertNode, questions: Map<number, Question>): EditorNode[] {
  switch (spec.type) {
    case 'rich_text':
      return spec.rich_doc_blocks.map((block) => {
        const node = createRichTextNode()
        node.content = block
        // 画布每行恰好一个顶层块，与后端拆块口径一致。
        node.schemaVersion = 2
        return node
      })
    case 'heading': {
      const node = createHeadingNode(spec.level)
      node.content = headingTextToDoc(spec.text)
      node.schemaVersion = 2
      return [node]
    }
    case 'question': {
      const question = questions.get(spec.question_id)
      if (!question) {
        throw new Error(`题库里找不到 id 为 ${spec.question_id} 的题目（可能已删除或不属于本学科）。`)
      }
      let node = createQuestionNode(question)
      if (spec.number != null) node = { ...node, props: questionPropsWithNumber(node, String(spec.number)) }
      if (spec.score != null) node = { ...node, props: questionPropsWithScore(node, spec.score) }
      return [node]
    }
    case 'answer_space':
      return [createAnswerSpaceNode(spec.lines, spec.style)]
    case 'page_break':
      return [createPageBreakNode()]
  }
}

function applyInsert(
  doc: EditorDocument,
  op: Extract<AiOperation, { op: 'insert_nodes' }>,
  questions: Map<number, Question>,
): { doc: EditorDocument; message: string } {
  const index = resolveAnchor(doc, op.after)
  const nodes = op.nodes.flatMap((spec) => buildInsertNode(spec, questions))
  return { doc: insertRootNodesAfter(doc, index, nodes), message: `已插入 ${nodes.length} 个节点。` }
}

function applyRemove(
  doc: EditorDocument,
  op: Extract<AiOperation, { op: 'remove_nodes' }>,
): { doc: EditorDocument; message: string } {
  const doomed = new Set<string>()
  for (const id of op.node_ids) {
    if (rootIndexOf(doc, id) >= 0) {
      doomed.add(id)
      continue
    }
    if (isModuleChild(doc, id)) {
      // answer_item 由 normalizeDocument 按 module scope 派生，删了立刻会长回来。
      throw new Error(`节点 ${id} 是参考答案模块内的派生节点，不能单独删除；要去掉它请删除对应的题目或整个模块。`)
    }
    throw new Error(`找不到节点 ${id}，请先用 read_composition_outline 获取最新的节点 id。`)
  }
  // 被删题目的 answer_item 由末尾的规范化自动回收。
  const nodes = doc.nodes.filter((n) => !doomed.has(n.id))
  return { doc: normalizeDocument({ nodes }), message: `已删除 ${doomed.size} 个节点。` }
}

function applyMove(
  doc: EditorDocument,
  op: Extract<AiOperation, { op: 'move_node' }>,
): { doc: EditorDocument; message: string } {
  const from = rootIndexOf(doc, op.node_id)
  if (from < 0) requireRootNode(doc, op.node_id)
  if (op.before === op.node_id) throw new Error('不能把节点移到它自己之前。')

  const rest = doc.nodes.slice()
  const [moved] = rest.splice(from, 1)
  let at = rest.length
  if (op.before != null) {
    at = rest.findIndex((n) => n.id === op.before)
    if (at < 0) {
      throw new Error(`找不到落点节点 ${op.before}，请先用 read_composition_outline 获取最新的节点 id。`)
    }
  }
  rest.splice(at, 0, moved!)
  return { doc: normalizeDocument({ nodes: rest }), message: '已移动节点。' }
}

function applySetProps(
  doc: EditorDocument,
  op: Extract<AiOperation, { op: 'set_node_props' }>,
): { doc: EditorDocument; message: string } {
  const node = requireRootNode(doc, op.node_id)
  const allowed = SETTABLE_BY_TYPE[node.nodeType]
  if (!allowed) throw new Error(`${node.nodeType} 节点没有可修改的属性。`)

  const touched = [...Object.keys(op.props), ...op.clear]
  const unknown = touched.filter((k) => !allowed.includes(k))
  if (unknown.length) {
    throw new Error(`${node.nodeType} 节点只支持修改 ${allowed.join('/')}，不支持 ${unknown.join('/')}。`)
  }

  const cleared = new Set(op.clear)
  let props = node.props

  if (node.nodeType === 'question') {
    let staged: EditorNode = node
    if ('number' in op.props || cleared.has('number')) {
      const value = cleared.has('number') ? '' : String(op.props.number)
      staged = { ...staged, props: questionPropsWithNumber(staged, value) }
    }
    if ('score' in op.props || cleared.has('score')) {
      const value = cleared.has('score') ? null : Number(op.props.score)
      staged = { ...staged, props: questionPropsWithScore(staged, value) }
    }
    props = staged.props
  } else if (node.nodeType === 'heading') {
    props = { level: (op.props.level ?? 2) as HeadingLevel } satisfies HeadingProps
  } else if (node.nodeType === 'answer_space') {
    const cur = answerSpacePropsOf(node)
    props = {
      lines: op.props.lines != null ? Number(op.props.lines) : cur.lines,
      style: (op.props.style ?? cur.style) as AnswerSpaceStyle,
    }
  } else {
    const cur = detailPropsOf(node)
    props = {
      scope: (op.props.scope ?? cur.scope) as DetailScope,
      fields: (op.props.fields ?? cur.fields) as Record<AnswerFieldKey, boolean>,
    } satisfies QuestionDetailsProps
  }

  return { doc: normalizeDocument(patchNode(doc, node.id, { props })), message: '已更新节点属性。' }
}

function applyShowFields(
  doc: EditorDocument,
  op: Extract<AiOperation, { op: 'show_question_fields' }>,
): { doc: EditorDocument; message: string } {
  const node = requireRootNode(doc, op.node_id)
  if (node.nodeType !== 'question') throw new Error(`节点 ${op.node_id} 不是题目，无法设置字段显隐。`)

  let staged: EditorNode = node
  const changed: string[] = []
  for (const key of ANSWER_FIELD_KEYS) {
    const value = op.show[key]
    if (!value) continue
    // inherit → null，回落到稿件级的 question_display 开关。
    staged = { ...staged, props: questionPropsWithShow(staged, key, value === 'inherit' ? null : value === 'show') }
    changed.push(`${key}=${value}`)
  }
  if (!changed.length) throw new Error('show 里没有任何可识别的字段。')
  return {
    doc: patchNode(doc, node.id, { props: staged.props }),
    message: `已设置题目字段显隐（${changed.join('，')}）。`,
  }
}

function applyAddDetailsModule(
  doc: EditorDocument,
  op: Extract<AiOperation, { op: 'add_details_module' }>,
): { doc: EditorDocument; message: string } {
  const index = resolveAnchor(doc, op.after)
  const heading = createHeadingNode(2)
  heading.content = headingTextToDoc(op.title)
  heading.schemaVersion = 2
  const moduleNode = createQuestionDetailsModule(op.scope, op.fields)
  // 标题作为模块前的同级块，而不是 module 的 children —— 画布（convert.ts 的 A-slim）
  // 加载时本就会把模块内的自定义块上提成同级块，直接写成最终形态免得一打开就变形。
  // answer_item 子节点由规范化按 scope 派生，不在这里手搓。
  return {
    doc: insertRootNodesAfter(doc, index, [heading, moduleNode]),
    message: `已添加「${op.title}」模块。`,
  }
}

/** 收集所有待插入题目的 id，一次性取实时数据（content 是冻结快照，不能信缓存）。 */
function collectQuestionIds(ops: AiOperation[]): number[] {
  const ids = new Set<number>()
  for (const op of ops) {
    if (op.op !== 'insert_nodes') continue
    for (const node of op.nodes) {
      if (node.type === 'question') ids.add(node.question_id)
    }
  }
  return [...ids]
}

/** 按顺序应用一批原语。单条失败不中断其余操作，末尾统一规范化一次。 */
export async function applyOperations(
  doc: EditorDocument,
  ops: AiOperation[],
  deps: ApplyDeps,
): Promise<ApplyOutcome> {
  const questions = new Map<number, Question>()
  const ids = collectQuestionIds(ops)
  if (ids.length) {
    for (const q of await deps.loadQuestions(ids)) questions.set(q.id, q)
  }

  let current = doc
  const results: OperationResult[] = []
  for (const op of ops) {
    try {
      let step: { doc: EditorDocument; message: string }
      switch (op.op) {
        case 'insert_nodes': step = applyInsert(current, op, questions); break
        case 'remove_nodes': step = applyRemove(current, op); break
        case 'move_node': step = applyMove(current, op); break
        case 'set_node_props': step = applySetProps(current, op); break
        case 'show_question_fields': step = applyShowFields(current, op); break
        case 'add_details_module': step = applyAddDetailsModule(current, op); break
        default: throw new Error(`不支持的操作：${(op as { op: string }).op}`)
      }
      current = step.doc
      results.push({ op: op.op, ok: true, message: step.message })
    } catch (e: any) {
      results.push({ op: op.op, ok: false, message: e?.message ?? String(e) })
    }
  }

  return { doc: normalizeDocument(current), results }
}
