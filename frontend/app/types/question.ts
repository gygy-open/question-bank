import type { RichDoc } from './richContent'

/** 五种题型，取值与后端 QuestionType 枚举一一对应。 */
export type QuestionType =
  | 'single_choice'
  | 'multiple_choice'
  | 'true_false'
  | 'fill_in_the_blank'
  | 'free_response'

export type QuestionStatus = 'draft' | 'pending' | 'published' | 'archived'

/** 选择题选项：content 为富文本，label 是展示字母（A/B/…），id 为稳定引用键。 */
export interface OptionSpec {
  id: string
  label: string
  content: RichDoc
}

export interface SingleChoiceAnswer {
  kind: 'single_choice'
  correct: string
}

export interface MultipleChoiceAnswer {
  kind: 'multiple_choice'
  correct: string[]
  grading?: 'all_or_nothing' | 'partial' | null
}

export interface TrueFalseAnswer {
  kind: 'true_false'
  correct: boolean
}

/** 单个填空的可接受答案集合与匹配策略。 */
export interface Blank {
  id: string
  accept: RichDoc[]
  match?: 'exact' | 'ignore_space' | 'ignore_case' | 'numeric' | null
}

export interface FillBlankAnswer {
  kind: 'fill_in_the_blank'
  blanks: Blank[]
}

export interface FreeResponseAnswer {
  kind: 'free_response'
  reference: RichDoc
}

/** 只读态：旧数据未解析的答案。仅用于展示，写请求禁止出现。 */
export interface LegacyUnresolvedAnswer {
  kind: 'legacy_unresolved'
  expected_kind: QuestionType
  raw: RichDoc
}

/** answer 判别联合（读取侧含 legacy_unresolved）。 */
export type AnswerSpec =
  | SingleChoiceAnswer
  | MultipleChoiceAnswer
  | TrueFalseAnswer
  | FillBlankAnswer
  | FreeResponseAnswer
  | LegacyUnresolvedAnswer
