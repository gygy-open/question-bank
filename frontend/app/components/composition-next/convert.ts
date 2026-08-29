// 组稿「行 ⇄ 单一 tiptap 文档」转换（Phase 0 Spike）。
// 顶层块 = 一行 EditorNode：uid 承载行身份。多块 rich_text（历史遗留）在入向被拆成多块，
// 首块沿用行 id、其余分配新 UUID——这正是「段落级独立节点」的落地形态。
import type { EditorDocument, EditorNode } from '@/lib/compositionDocument'
import { generateNodeId } from '@/lib/compositionDocument'
import type {
  CompositionNodeType,
  HeadingProps,
  QuestionContentSnapshot,
  QuestionDetailsProps,
  QuestionProps,
} from '@/types/composition'
import type { RichDocNode, RichNode } from '@/types'

const UID_ATTR = 'uid'

function makeNode(nodeType: CompositionNodeType): EditorNode {
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

/** 附加/覆盖 uid 属性。 */
function withUid(block: RichNode, uid: string): RichNode {
  return { ...block, attrs: { ...(block.attrs ?? {}), [UID_ATTR]: uid } }
}

/** 剥离 uid（存回行 content 时块自身不应携带 uid，身份归行 id）。 */
function stripUid(block: RichNode): RichNode {
  if (!block.attrs || !(UID_ATTR in block.attrs)) return block
  const { [UID_ATTR]: _drop, ...rest } = block.attrs
  const clone: RichNode = { ...block }
  if (Object.keys(rest).length) clone.attrs = rest
  else delete clone.attrs
  return clone
}

// --------------------------------------------------------------------------- //
// 行 → PM 文档
// --------------------------------------------------------------------------- //

function headingRowToPm(node: EditorNode): RichNode {
  const para = node.content?.content?.[0]
  const textAlign = para?.attrs?.textAlign
  const attrs: Record<string, unknown> = {
    [UID_ATTR]: node.id,
    level: (node.props as HeadingProps | null)?.level ?? 2,
  }
  if (textAlign) attrs.textAlign = textAlign
  return { type: 'heading', attrs, content: para?.content ?? [] }
}

function questionRowToPm(node: EditorNode): RichNode {
  return {
    type: 'question',
    attrs: {
      [UID_ATTR]: node.id,
      questionId: node.questionId,
      questionRevision: node.questionRevision,
      snapshot: node.questionContent,
      props: node.props,
    },
  }
}

/** 把编辑态文档序列化为单一 PM doc（供 tiptap setContent）。 */
export function editorDocumentToPmDoc(doc: EditorDocument): RichDocNode {
  const content: RichNode[] = []
  for (const node of doc.nodes) {
    switch (node.nodeType) {
      case 'heading':
        content.push(headingRowToPm(node))
        break
      case 'question':
        content.push(questionRowToPm(node))
        break
      case 'page_break':
        content.push({ type: 'pageBreak', attrs: { [UID_ATTR]: node.id } })
        break
      case 'question_details':
        pushModuleAslim(content, node)
        break
      case 'rich_text': {
        const blocks = node.content?.content ?? []
        blocks.forEach((block, i) => {
          content.push(withUid(block, i === 0 ? node.id : generateNodeId()))
        })
        break
      }
      // question_details 等暂以不透明块无损承载。
      default:
        content.push({
          type: 'opaqueBlock',
          attrs: { [UID_ATTR]: node.id, node: serializeOpaque(node) },
        })
    }
  }
  // 一次性去响应式化：本函数仅在加载/外部 setContent 时运行（非逐键），拷贝成本可忽略。
  return jsonClone({ type: 'doc', content })
}

function serializeOpaque(node: EditorNode): Omit<EditorNode, 'id'> {
  const { id: _id, ...rest } = node
  return jsonClone(rest)
}

// 节点内容全是纯 JSON；用 JSON 深拷贝而非 structuredClone，避免 Vue 响应式 proxy 触发 DataCloneError。
function jsonClone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

// --------------------------------------------------------------------------- //
// 模块（question_details）⇄ 原生内容
// --------------------------------------------------------------------------- //

const DEFAULT_MODULE_PROPS: QuestionDetailsProps = {
  scope: 'all',
  fields: { answer: true, thinking: false, analysis: false, summary: false },
}

/** A-slim：模块内自定义块上提为模块前的顶层块（迁移），answer_item 丢弃（改由 NodeView 派生）；模块本身为无内容 atom。 */
function pushModuleAslim(content: RichNode[], node: EditorNode): void {
  for (const c of node.children ?? []) {
    if (c.nodeType === 'heading') {
      content.push(headingRowToPm(c))
    } else if (c.nodeType === 'rich_text') {
      const blocks = c.content?.content ?? []
      if (blocks.length) blocks.forEach((b, i) => content.push(withUid(b, i === 0 ? c.id : generateNodeId())))
      else content.push({ type: 'paragraph', attrs: { [UID_ATTR]: c.id } })
    }
    // answer_item：丢弃（由模块 NodeView 按 scope 实时派生）。
  }
  content.push({ type: 'questionDetails', attrs: { [UID_ATTR]: node.id, props: node.props ?? DEFAULT_MODULE_PROPS } })
}

// --------------------------------------------------------------------------- //
// PM 文档 → 行
// --------------------------------------------------------------------------- //

function pmHeadingToRow(block: RichNode): EditorNode {
  const node = makeNode('heading')
  const uid = block.attrs?.[UID_ATTR]
  if (typeof uid === 'string') node.id = uid
  node.props = { level: (block.attrs?.level as HeadingProps['level']) ?? 2 }
  const para: RichNode = { type: 'paragraph', content: block.content ?? [] }
  if (block.attrs?.textAlign) para.attrs = { textAlign: block.attrs.textAlign }
  node.content = { type: 'doc', content: [para] }
  // 单文档来源标记（与 rich_text 一致），供保存往返与空块豁免识别。
  node.schemaVersion = 2
  return node
}

function pmQuestionToRow(block: RichNode): EditorNode {
  const node = makeNode('question')
  const uid = block.attrs?.[UID_ATTR]
  if (typeof uid === 'string') node.id = uid
  node.questionId = (block.attrs?.questionId as number | null) ?? null
  node.questionRevision = (block.attrs?.questionRevision as number | null) ?? null
  node.questionContent = (block.attrs?.snapshot as QuestionContentSnapshot | null) ?? null
  node.props = (block.attrs?.props as QuestionProps | null) ?? null
  return node
}

/** 把单一 PM doc 反序列化为编辑态文档（供保存/派生）。 */
export function pmDocToEditorDocument(pmDoc: RichDocNode): EditorDocument {
  const nodes: EditorNode[] = []
  for (const block of pmDoc.content ?? []) {
    const uid = block.attrs?.[UID_ATTR]
    switch (block.type) {
      case 'heading':
        nodes.push(pmHeadingToRow(block))
        break
      case 'question':
        nodes.push(pmQuestionToRow(block))
        break
      case 'pageBreak': {
        const node = makeNode('page_break')
        if (typeof uid === 'string') node.id = uid
        nodes.push(node)
        break
      }
      case 'questionDetails': {
        // A-slim：模块为无内容 atom；children 留空，answer_item 由服务端派生。
        const node = makeNode('question_details')
        if (typeof uid === 'string') node.id = uid
        node.props = (block.attrs?.props as QuestionDetailsProps | null) ?? null
        nodes.push(node)
        break
      }
      case 'opaqueBlock': {
        const stored = block.attrs?.node as Omit<EditorNode, 'id'> | null
        const node: EditorNode = { ...(jsonClone(stored) as EditorNode), id: typeof uid === 'string' ? uid : generateNodeId() }
        nodes.push(node)
        break
      }
      default: {
        const node = makeNode('rich_text')
        if (typeof uid === 'string') node.id = uid
        node.content = { type: 'doc', content: [stripUid(block)] }
        // 单文档画布保证每行恰好一个顶层块，标记 schema_version=2 让不变量数据自证。
        node.schemaVersion = 2
        nodes.push(node)
      }
    }
  }
  return { nodes }
}
