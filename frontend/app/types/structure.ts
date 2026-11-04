/**
 * 题干结构化(规格 docs/specs/question-structure.md)的前端类型。
 *
 * 一道题(或一份材料)的题干被拆成「条件」与「设问」,每条按学科的元素类型树归类;
 * 每次拆解是一条快照(run),只有「已采纳」的参与检索与统计。
 */

/** 拆解的对象:题目或材料。 */
export type StructTargetType = 'question' | 'stimulus'

/** 题库列表徽标用的结构状态。 */
export type StructState = 'none' | 'draft' | 'accepted' | 'stale'

/** 一次拆解快照的审核状态。 */
export type StructRunState = 'draft' | 'accepted' | 'rejected' | 'superseded'

/** 条件的作用:给值 / 给关系 / 在动或可变 / 研究对象本身。 */
export type StructFacet = 'quant' | 'qual' | 'proc' | 'form'

/** 元素类型树的节点用于条件还是设问。 */
export type StructTypeKind = 'condition' | 'ask'

/** 元素类型的状态:只有 active 会提供给 AI、出现在筛选里。 */
export type StructTypeStatus = 'candidate' | 'active' | 'deprecated'

/** 体检问题(app/services/structure/check.py)。 */
export interface StructCheckIssue {
  code: 'empty' | 'span_not_found' | 'duplicate' | 'dangling_symbol' | 'compound' | 'uncovered' | string
  severity: 'error' | 'warning' | 'info'
  /** 针对的条目:条件 / 设问;为 null 时针对整个题干。 */
  target: 'element' | 'ask' | null
  /** 条目在条件 / 设问列表中的下标。 */
  index: number | null
  message: string
  detail: string
}

export interface StructCheckReport {
  ok: boolean
  errors: number
  warnings: number
  /** 被条目覆盖的实义文字占比(0~1)。 */
  coverage: number
  /** 没被任何条目覆盖的实义文字。 */
  residual: string
  issues: StructCheckIssue[]
}

/** 一条条件。 */
export interface StructElement {
  id: number
  ordinal: number
  content: string
  type_id: number | null
  /** 从根到该类型的名称路径,如 ["代数", "函数"]。 */
  type_path: string[]
  /** 未归类时 AI 给出的类型描述,留给归纳。 */
  type_hint: string | null
  facet: StructFacet | null
  /** 在快照 stem_text 中的 [start, end);引用材料条件时为 null。 */
  span: [number, number] | null
  ref_element_id: number | null
  /** 引用自哪份材料(共享条件)。 */
  shared_from_stimulus_id: number | null
}

/** 一条设问。 */
export interface StructAsk {
  id: number
  ordinal: number
  content: string
  type_id: number | null
  type_path: string[]
  type_hint: string | null
  span: [number, number] | null
  /** 依赖的条件 id。 */
  depends_on: number[]
}

/** 一次拆解快照。 */
export interface StructRun {
  id: number
  target_type: StructTargetType
  target_id: number
  subject_id: number | null
  source_revision: number
  /** 拆解之后题目又被修改过。 */
  stale: boolean
  /** 拆解时的题干纯文本快照(公式保留 $...$),所有 span 都指向它。 */
  stem_text: string
  origin: 'ai' | 'human'
  model: string | null
  prompt_version: string | null
  state: StructRunState
  check_report: StructCheckReport | null
  check_errors: number
  check_warnings: number
  created_by: number | null
  reviewed_by: number | null
  reviewed_at: string | null
  created_at: string
  elements: StructElement[]
  asks: StructAsk[]
}

/** 进行中的拆解任务。 */
export interface StructJob {
  id: number
  status: 'pending' | 'running' | 'paused'
  paused_reason: string | null
  error: string | null
  queue_ahead: number | null
}

/** 一道题(或一份材料)的结构化全貌。 */
export interface StructureView {
  target_type: StructTargetType
  target_id: number
  subject_id: number | null
  current_revision: number
  stimulus_id: number | null
  enabled: boolean
  accepted: StructRun | null
  draft: StructRun | null
  job: StructJob | null
}

/** 元素类型树的一个节点(扁平列表,parent_id 表示层级)。 */
export interface StructType {
  id: number
  subject_id: number
  parent_id: number | null
  kind: StructTypeKind
  code: string
  name: string
  definition: string | null
  examples: Array<{ text: string, positive?: boolean }> | null
  status: StructTypeStatus
  sort_order: number
  /** 被多少道已采纳的题 / 材料引用。 */
  usage: number
}

/** 人工编辑时提交的一条条件或设问。 */
export interface StructItemInput {
  content: string
  source?: string | null
  span_start?: number | null
  span_end?: number | null
  type_id?: number | null
  type_hint?: string | null
  facet?: StructFacet | null
  ref_element_id?: number | null
  /** 仅设问:依赖的条件在 elements 中的下标。 */
  depends_on?: number[]
}

export interface StructSavePayload {
  target_type: StructTargetType
  target_id: number
  base_run_id?: number | null
  elements: StructItemInput[]
  asks: StructItemInput[]
  accept?: boolean
}

/** 审核队列的一项。 */
export interface StructReviewQueueItem {
  id: number
  target_type: StructTargetType
  target_id: number
  origin: 'ai' | 'human'
  model: string | null
  check_errors: number
  check_warnings: number
  preview: string
  created_at: string
}

export interface StructReviewQueuePage {
  items: StructReviewQueueItem[]
  total: number
  page: number
  size: number
  pages: number
}

/** 同结构题。 */
export interface StructSimilarItem {
  question_id: number
  score: number
  shared_type_ids: number[]
  q_type: string
  preview: string
}

/** 学科结构化统计(首页卡片)。 */
export interface StructStats {
  total: number
  states: Record<StructState, number>
  queued: number
  unclassified: number
  top_types: Array<{ type_id: number, kind: StructTypeKind, path: string[], count: number }>
}

/** 一组题的元素类型分布(组卷侧栏)。 */
export interface StructDistribution {
  questions: number
  structured: number
  domains: Array<{ type_id: number, name: string, kind: StructTypeKind, count: number }>
  types: Array<{ type_id: number, path: string[], kind: StructTypeKind, count: number }>
}

/** 结构化开关与当前用户在学科内的权限。 */
export interface StructSettings {
  enabled: boolean
  can_manage_global: boolean
  auto_decompose?: boolean
  can_manage_subject?: boolean
  can_edit_types?: boolean
  can_edit?: boolean
}
