import type { DisplayField, DisplayRegion, DisplayPolicy, QuestionBrief } from '~/types'

/** 字段顺序 + 标签 + 取值来源 (集中消化 thinking/analysis 命名错位)。 */
export const FIELD_ORDER: DisplayField[] = ['answer', 'analysis', 'explanation', 'summary', 'source']

export const FIELD_LABEL: Record<DisplayField, string> = {
  answer: '答案',
  analysis: '分析',
  explanation: '解析',
  summary: '总结',
  source: '来源',
}

const FIELD_SOURCE: Record<DisplayField, keyof QuestionBrief> = {
  answer: 'answer',
  analysis: 'thinking',
  explanation: 'analysis',
  summary: 'summary',
  source: 'source',
}

export const REGION_LABEL: Record<DisplayRegion, string> = {
  inline: '题后',
  appendix: '卷末',
  hidden: '不显示',
}

/** 字段含义提示 (辅助区分命名易混淆的 分析/解析)。 */
export const FIELD_HINT: Record<DisplayField, string> = {
  answer: '题目的正确答案',
  analysis: '解题思路（题库中的"思路"内容）',
  explanation: '详细解析过程',
  summary: '本题考点小结',
  source: '题目出处来源',
}

export interface DocumentPreset {
  value: string
  label: string
  regions: Partial<Record<DisplayField, DisplayRegion>>
}

/** 文档级快捷预设: 一键铺满 5 个字段的显示策略。 */
export const DOCUMENT_PRESETS: DocumentPreset[] = [
  { value: 'blank', label: '仅题干', regions: {} },
  { value: 'answer_inline', label: '答案跟题', regions: { answer: 'inline', explanation: 'inline' } },
  { value: 'answer_appendix', label: '答案卷末', regions: { answer: 'appendix', explanation: 'appendix' } },
]

const SYSTEM_DEFAULT: DisplayRegion = 'hidden'

const regionOf = (display: DisplayPolicy | null | undefined, field: DisplayField): DisplayRegion | undefined =>
  display?.fields?.[field]?.region

/** 逐字段级联: 题块覆盖 > 文档默认 > 系统兜底。 */
export const resolveRegion = (
  field: DisplayField,
  blockDisplay: DisplayPolicy | null | undefined,
  docDisplay: DisplayPolicy | null | undefined,
): DisplayRegion => regionOf(blockDisplay, field) ?? regionOf(docDisplay, field) ?? SYSTEM_DEFAULT

/** 便捷构造完整文档级策略。 */
export const makeDisplay = (regions: Partial<Record<DisplayField, DisplayRegion>>): DisplayPolicy => ({
  v: 1,
  fields: Object.fromEntries(
    FIELD_ORDER.map((f) => [f, { region: regions[f] ?? SYSTEM_DEFAULT }]),
  ) as DisplayPolicy['fields'],
})

/** 取题目某字段的值 (用于编辑器内联预览)。 */
export const fieldValue = (q: QuestionBrief, field: DisplayField): string | null | undefined =>
  q[FIELD_SOURCE[field]] as string | null | undefined
