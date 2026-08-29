// 单文档画布 → 题目 NodeView 的全局显示上下文（题号/赋分开关、全局字段显隐）。
// canvas 从页面 props 派生并 provide；NodeView inject（带缺省，脱离 canvas 时降级只读）。
import type { InjectionKey, Ref } from 'vue'
import { ref } from 'vue'
import type { AnswerFieldKey, QuestionRevisionStatus } from '@/types/composition'

export const NUMBERING_ENABLED_KEY: InjectionKey<Ref<boolean>> = Symbol('composition-numbering')
export const SCORING_ENABLED_KEY: InjectionKey<Ref<boolean>> = Symbol('composition-scoring')
export const DISPLAY_FIELDS_KEY: InjectionKey<Ref<Record<AnswerFieldKey, boolean>>> =
  Symbol('composition-display-fields')

// 题目版本状态（question_id → 实时 revision/可用性），用于 stale/deleted 标记与「同步此题」。
export const QUESTION_STATUS_KEY: InjectionKey<Ref<Map<number, QuestionRevisionStatus>>> =
  Symbol('composition-question-status')
// 请求同步指定 question 节点 UUID（NodeView → canvas → 页面）。
export const SYNC_QUESTIONS_KEY: InjectionKey<(nodeIds: string[]) => void> =
  Symbol('composition-sync-questions')
// 同步禁用（有未保存修改或正在同步）。
export const SYNC_DISABLED_KEY: InjectionKey<Ref<boolean>> = Symbol('composition-sync-disabled')

// 有序根节点（含题目快照），供模块按 scope + 自身位置实时派生答案列表。
export const ROOT_NODES_KEY: InjectionKey<Ref<EditorNodeLike[]>> =
  Symbol('composition-root-nodes')

// 避免与 lib/compositionDocument 形成导入环：此处仅需最小结构。
export interface EditorNodeLike {
  id: string
  nodeType: string
  questionId: number | null
  questionRevision: number | null
  questionContent: unknown
  props: unknown
}

export function defaultDisplayFields(): Record<AnswerFieldKey, boolean> {
  return { answer: false, thinking: false, analysis: false, summary: false }
}

export const FALLBACK_NUMBERING = ref(false)
export const FALLBACK_SCORING = ref(false)
export const FALLBACK_DISPLAY = ref(defaultDisplayFields())
export const FALLBACK_STATUS = ref(new Map<number, QuestionRevisionStatus>())
export const FALLBACK_SYNC_DISABLED = ref(true)
export const noopSync = (_ids: string[]) => {}
export const FALLBACK_ROOT_NODES = ref([] as EditorNodeLike[])
