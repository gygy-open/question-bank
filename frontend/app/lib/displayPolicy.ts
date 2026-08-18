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

/** 例题预设: 答案 + 分析内联。 */
export const EXAMPLE_OVERRIDE: DisplayPolicy = {
  fields: { answer: { region: 'inline' }, analysis: { region: 'inline' } },
}
