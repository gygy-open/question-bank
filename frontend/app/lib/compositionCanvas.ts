// 组稿画布纯函数：编辑态 block 模型、批量替换载荷、线性重排、脏检测、heading 富文本转换。
// 不依赖 Nuxt 运行时，便于聚焦单测（与后端 app/schemas/composition.py 契约对齐）。

import type {
  AnswerSummaryMode,
  CompositionBlock,
  CompositionBlockReplaceItem,
  CompositionBlocksReplaceRequest,
  CompositionBlocksReplaceResponse,
  CompositionBlockType,
  HeadingLevel,
} from '@/types/composition'
import type { RichDocNode, RichNode } from '@/types'
import { isEmptyRichDoc } from '@/components/rich-editor/richDoc'

/** 编辑态 block：serverId 为空表示新建；key 是稳定的本地渲染键，也用作 temp_id。 */
export interface EditorBlock {
  key: string
  serverId: number | null
  blockType: CompositionBlockType
  content: RichDocNode | null
  props: { level?: HeadingLevel; mode?: AnswerSummaryMode } | null
  questionId: number | null
  questionRevision: number | null
}

let keyCounter = 0

/** 生成稳定唯一的本地 key（优先 crypto.randomUUID，回退计数器+随机）。 */
export function generateBlockKey(): string {
  const g = globalThis as { crypto?: { randomUUID?: () => string } }
  if (g.crypto?.randomUUID) {
    return `blk_${g.crypto.randomUUID()}`
  }
  keyCounter += 1
  return `blk_${Date.now().toString(36)}_${keyCounter}_${Math.random().toString(36).slice(2, 8)}`
}

function emptyParagraphDoc(): RichDocNode {
  return { type: 'doc', content: [{ type: 'paragraph' }] }
}

/** 新建指定类型的编辑态 block，带该类型的合理默认值。 */
export function newEditorBlock(type: CompositionBlockType): EditorBlock {
  const base: EditorBlock = {
    key: generateBlockKey(),
    serverId: null,
    blockType: type,
    content: null,
    props: null,
    questionId: null,
    questionRevision: null,
  }
  if (type === 'rich_text') {
    base.content = emptyParagraphDoc()
  } else if (type === 'heading') {
    base.content = emptyParagraphDoc()
    base.props = { level: 2 }
  } else if (type === 'answer_summary') {
    base.props = { mode: 'all' }
  }
  return base
}

/** 由服务端返回的单个 block 构造编辑态（生成新 key）。 */
export function editorBlockFromRead(block: CompositionBlock): EditorBlock {
  return {
    key: generateBlockKey(),
    serverId: block.id,
    blockType: block.block_type,
    content: block.content ?? null,
    props:
      block.block_type === 'heading'
        ? { level: block.props.level }
        : block.block_type === 'answer_summary'
          ? { mode: block.props.mode }
          : null,
    questionId: block.block_type === 'question' ? block.question_id : null,
    questionRevision: block.block_type === 'question' ? block.question_revision : null,
  }
}

/** 由 detail.blocks 构造有序编辑态数组。 */
export function editorBlocksFromDetail(blocks: CompositionBlock[]): EditorBlock[] {
  return blocks.map(editorBlockFromRead)
}

/** 把编辑态 block 序列化为一个批量替换 item（新建用 temp_id=key，已有用 id）。 */
export function blockToReplaceItem(block: EditorBlock): CompositionBlockReplaceItem {
  const item: CompositionBlockReplaceItem = { block_type: block.blockType }
  if (block.serverId != null) {
    item.id = block.serverId
  } else {
    item.temp_id = block.key
  }
  switch (block.blockType) {
    case 'rich_text':
      item.content = block.content
      break
    case 'heading':
      item.content = block.content
      item.props = { level: block.props?.level ?? 2 }
      break
    case 'question':
      // question_revision 由服务端钉住，这里带上仅为可读；服务端会覆盖。
      item.question_id = block.questionId
      item.question_revision = block.questionRevision
      break
    case 'answer_summary':
      item.props = { mode: block.props?.mode ?? 'all' }
      break
    case 'page_break':
      break
  }
  return item
}

/** 构造整段替换请求体。 */
export function blocksToReplaceRequest(
  blocks: EditorBlock[],
  expectedRevision: number,
  batchId?: string,
): CompositionBlocksReplaceRequest {
  const payload: CompositionBlocksReplaceRequest = {
    expected_revision: expectedRevision,
    blocks: blocks.map(blockToReplaceItem),
  }
  if (batchId) payload.batch_id = batchId
  return payload
}

/** 保存成功后用响应重建编辑态，尽量保留原有本地 key（避免组件重挂）。 */
export function reconcileAfterSave(
  prev: EditorBlock[],
  resp: CompositionBlocksReplaceResponse,
): EditorBlock[] {
  const prevByServerId = new Map<number, EditorBlock>()
  for (const b of prev) {
    if (b.serverId != null) prevByServerId.set(b.serverId, b)
  }
  // 反转 id_map：新 serverId → 原 temp_id（即原 key）。
  const serverIdToTempKey = new Map<number, string>()
  for (const [tempKey, serverId] of Object.entries(resp.id_map)) {
    serverIdToTempKey.set(serverId, tempKey)
  }
  return resp.blocks.map((read) => {
    const next = editorBlockFromRead(read)
    const preservedKey = prevByServerId.get(read.id)?.key ?? serverIdToTempKey.get(read.id)
    if (preservedKey) next.key = preservedKey
    return next
  })
}

/** 上/下移动 index 处的 block；越界或方向无效时返回原数组的浅拷贝。 */
export function moveBlock(
  blocks: EditorBlock[],
  index: number,
  direction: 'up' | 'down',
): EditorBlock[] {
  const target = direction === 'up' ? index - 1 : index + 1
  if (index < 0 || index >= blocks.length || target < 0 || target >= blocks.length) {
    return blocks.slice()
  }
  const next = blocks.slice()
  const tmp = next[index]!
  next[index] = next[target]!
  next[target] = tmp
  return next
}

/** 删除指定 key 的 block。 */
export function removeBlock(blocks: EditorBlock[], key: string): EditorBlock[] {
  return blocks.filter((b) => b.key !== key)
}

/** 在 index 之后插入 block；index<0 时插到最前，越界时追加到末尾。 */
export function insertBlockAfter(
  blocks: EditorBlock[],
  index: number,
  block: EditorBlock,
): EditorBlock[] {
  const next = blocks.slice()
  const at = index < 0 ? 0 : Math.min(index + 1, next.length)
  next.splice(at, 0, block)
  return next
}

/** 脏检测快照：忽略本地 key / serverId / questionRevision（后者由服务端钉住）。 */
export function snapshotBlocks(blocks: EditorBlock[]): string {
  return JSON.stringify(
    blocks.map((b) => ({
      t: b.blockType,
      c: b.content,
      p: b.props,
      q: b.questionId,
    })),
  )
}

/** 保存前的阻断性问题：空的文本/标题块、缺失题目引用。返回人类可读描述列表。 */
export function collectBlockIssues(blocks: EditorBlock[]): string[] {
  const issues: string[] = []
  blocks.forEach((b, i) => {
    const at = `第 ${i + 1} 个块`
    if (b.blockType === 'rich_text' && isEmptyRichDoc(b.content)) {
      issues.push(`${at}（文本）内容为空`)
    } else if (b.blockType === 'heading' && isEmptyRichDoc(b.content)) {
      issues.push(`${at}（标题）内容为空`)
    } else if (b.blockType === 'question' && b.questionId == null) {
      issues.push(`${at}（题目）未选择题目`)
    }
  })
  return issues
}

// --- heading 富文本 <-> 纯文本转换（首期 heading 用单行文本编辑） --- //

/** 抽取 heading 首段的纯文本（用于文本输入回填）。 */
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

/** 纯文本转单段落 heading RichDoc（空文本 → 单个空段落，后端接受）。 */
export function headingTextToDoc(text: string): RichDocNode {
  const trimmed = text
  if (!trimmed) {
    return emptyParagraphDoc()
  }
  return {
    type: 'doc',
    content: [{ type: 'paragraph', content: [{ type: 'text', text: trimmed }] }],
  }
}

/** heading 首段是否含非纯文本行内节点（如公式）；用于提示纯文本编辑会丢失富内容。 */
export function headingHasRichInline(doc: RichDocNode | null | undefined): boolean {
  if (!doc || doc.type !== 'doc') return false
  const first = (doc.content ?? [])[0]
  if (!first || first.type !== 'paragraph') return false
  return (first.content ?? []).some(
    (node: RichNode) => node.type !== 'text',
  )
}
