import { Heading2, AlignLeft, SeparatorHorizontal } from '@lucide/vue'
import type { BlockType, QuestionBrief } from '~/types'
import HeadingBlock from './blocks/HeadingBlock.vue'
import TextBlock from './blocks/TextBlock.vue'
import QuestionBlock from './blocks/QuestionBlock.vue'
import PageBreakBlock from './blocks/PageBreakBlock.vue'

/** 编辑期的客户端块模型 (带稳定 key，供 v-for / 拖拽使用)。 */
export interface EditorBlock {
  key: string
  block_type: BlockType
  content: Record<string, any>
  ref_question_id?: number | null
  question?: QuestionBrief | null
}

export const blockRegistry: Record<BlockType, any> = {
  heading: HeadingBlock,
  text: TextBlock,
  question: QuestionBlock,
  page_break: PageBreakBlock,
}

export const getBlockComponent = (type: BlockType) => blockRegistry[type] ?? TextBlock

/** 可通过 “+” 菜单插入的非题目块类型。 */
export const insertableBlocks: { type: BlockType; label: string; icon: any }[] = [
  { type: 'text', label: '文本段落', icon: AlignLeft },
  { type: 'heading', label: '大题标题', icon: Heading2 },
  { type: 'page_break', label: '分页符', icon: SeparatorHorizontal },
]

const uid = (): string => {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `b-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

export const newEditorBlock = (type: BlockType): EditorBlock => {
  const base: EditorBlock = { key: uid(), block_type: type, content: {}, ref_question_id: null }
  if (type === 'heading') base.content = { text: '', level: 2 }
  else if (type === 'text') base.content = { text: '' }
  return base
}

/** 后端块 -> 编辑块。 */
export const toEditorBlock = (b: {
  block_type: BlockType
  content?: Record<string, any> | null
  ref_question_id?: number | null
  question?: QuestionBrief | null
}): EditorBlock => ({
  key: uid(),
  block_type: b.block_type,
  content: b.content ? { ...b.content } : {},
  ref_question_id: b.ref_question_id ?? null,
  question: b.question ?? null,
})

/** 编辑块 -> 保存负载。 */
export const toBlockWrite = (b: EditorBlock) => ({
  block_type: b.block_type,
  content: b.content && Object.keys(b.content).length ? b.content : null,
  ref_question_id: b.ref_question_id ?? null,
})
