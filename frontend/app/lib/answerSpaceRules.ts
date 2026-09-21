// 作答区默认值解析：与后端 app/services/answer_space.py 严格对称。
// 后端是唯一真源（学科覆盖存在 subject_settings），此处的默认值仅用于规则未加载时的降级。
import type { AnswerSpaceStyle } from '@/types/composition'

export interface AnswerSpaceRule {
  enabled: boolean
  min_lines: number
  lines_per_score: number
  max_lines: number
  style: AnswerSpaceStyle
}

export type AnswerSpaceRules = Record<string, AnswerSpaceRule>

export const ANSWER_SPACE_MAX_LINES = 50

export const DEFAULT_ANSWER_SPACE_RULES: AnswerSpaceRules = {
  single_choice: { enabled: false, min_lines: 1, lines_per_score: 0, max_lines: 1, style: 'blank' },
  multiple_choice: { enabled: false, min_lines: 1, lines_per_score: 0, max_lines: 1, style: 'blank' },
  true_false: { enabled: false, min_lines: 1, lines_per_score: 0, max_lines: 1, style: 'blank' },
  fill_in_the_blank: { enabled: true, min_lines: 1, lines_per_score: 0.5, max_lines: 3, style: 'blank' },
  free_response: { enabled: true, min_lines: 2, lines_per_score: 0.8, max_lines: 20, style: 'lined' },
}

const FALLBACK_RULE = DEFAULT_ANSWER_SPACE_RULES.free_response!

export function clampAnswerSpaceLines(lines: number): number {
  return Math.max(1, Math.min(ANSWER_SPACE_MAX_LINES, Math.round(lines)))
}

/** 该题型默认不配作答区时返回 null。 */
export function resolveAnswerSpaceProps(
  qType: string | null | undefined,
  score: number | null | undefined,
  rules: AnswerSpaceRules = DEFAULT_ANSWER_SPACE_RULES,
): { lines: number; style: AnswerSpaceStyle } | null {
  const rule = rules[qType ?? ''] ?? FALLBACK_RULE
  if (!rule.enabled) return null
  const raw = score == null || rule.lines_per_score <= 0
    ? rule.min_lines
    : Math.round(score * rule.lines_per_score)
  const lines = Math.max(rule.min_lines, Math.min(rule.max_lines, raw))
  return { lines: clampAnswerSpaceLines(lines), style: rule.style }
}

/** 用户显式插入作答区：即使题型默认不配，也给出一组可用值。 */
export function resolveAnswerSpacePropsOrFallback(
  qType: string | null | undefined,
  score: number | null | undefined,
  rules: AnswerSpaceRules = DEFAULT_ANSWER_SPACE_RULES,
): { lines: number; style: AnswerSpaceStyle } {
  return (
    resolveAnswerSpaceProps(qType, score, rules)
    ?? resolveAnswerSpaceProps(null, score, rules)
    ?? { lines: FALLBACK_RULE.min_lines, style: FALLBACK_RULE.style }
  )
}
