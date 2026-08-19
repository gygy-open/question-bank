import {
  Heading1, Heading2, Heading3, Heading4, AlignLeft, SeparatorHorizontal,
} from '@lucide/vue'
import type { BlockType, QuestionBrief } from '~/types'
import HeadingBlock from './blocks/HeadingBlock.vue'
import TextBlock from './blocks/TextBlock.vue'
import QuestionBlock from './blocks/QuestionBlock.vue'
import QuestionBlockMenu from './blocks/QuestionBlockMenu.vue'
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

/** 块类型的手柄菜单扩展项 (删除等通用项由 BlockCanvas 自己渲染, 这里只放类型专属操作)。 */
const blockMenuRegistry: Partial<Record<BlockType, any>> = {
  question: QuestionBlockMenu,
}

export const getBlockMenu = (type: BlockType) => blockMenuRegistry[type]

/** 可通过 “+” 菜单直接插入的静态块类型 (无需搜索)。 heading 的层级由 level 决定, 同一 block_type。 */
export const insertableBlocks: { type: BlockType; label: string; icon: any; level?: number }[] = [
  { type: 'heading', label: '标题 1', icon: Heading1, level: 1 },
  { type: 'heading', label: '标题 2', icon: Heading2, level: 2 },
  { type: 'heading', label: '标题 3', icon: Heading3, level: 3 },
  { type: 'heading', label: '标题 4', icon: Heading4, level: 4 },
  { type: 'text', label: '文本段落', icon: AlignLeft },
  { type: 'page_break', label: '分页符', icon: SeparatorHorizontal },
]

const uid = (): string => {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `b-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

export const newEditorBlock = (type: BlockType, level?: number): EditorBlock => {
  const base: EditorBlock = { key: uid(), block_type: type, content: {}, ref_question_id: null }
  if (type === 'heading') base.content = { text: '', level: level ?? 2 }
  else if (type === 'text') base.content = { text: '' }
  return base
}

/** 搜索选中一道题后, 就地生成可渲染的题目块 (无需刷新即可显示)。 */
export const newQuestionBlock = (question: QuestionBrief): EditorBlock => ({
  key: uid(),
  block_type: 'question',
  content: {},
  ref_question_id: question.id,
  question,
})

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
