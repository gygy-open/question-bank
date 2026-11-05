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
export type StructTypeKind = 'condition' | 'ask' | 'method'

/** 元素类型的状态:只有 active 会提供给 AI、出现在筛选里。 */
export type StructTypeStatus = 'candidate' | 'active' | 'deprecated'

/** 体检问题(app/services/structure/check.py)。 */
export interface StructCheckIssue {
  code: 'empty' | 'span_not_found' | 'duplicate' | 'dangling_symbol' | 'compound' | 'uncovered' | string
  severity: 'error' | 'warning' | 'info'
  /** 针对的条目:条件 / 设问;为 null 时针对整个题干。 */
  target: 'element' | 'ask' | 'param' | 'step' | null
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
  origin: StructOrigin
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
  /** 参数槽(可替换的值),用于生成变式。 */
  params: StructParam[]
  /** 元素组:几条条件作为整体,可整组替换。 */
  groups: StructElementGroup[]
}

/** 元素组。 */
export interface StructElementGroup {
  id: number
  ordinal: number
  name: string
  description: string | null
  replaceable: boolean
  element_ids: number[]
  /** 成员的类型组合;有未归类成员时不能参与替换匹配。 */
  type_ids: number[]
}

/** 保存时提交的元素组(成员用本次提交中条件的下标)。 */
export interface StructGroupInput {
  name: string
  description?: string | null
  replaceable?: boolean
  element_indices: number[]
}

/** 可替换进来的元素组。 */
export interface StructGroupCandidate {
  group_id: number
  question_id: number
  name: string
  contents: string[]
}

/** 命题 / 组替换任务的状态。 */
export interface StructComposeJob {
  id: number
  status: 'pending' | 'running' | 'paused' | 'succeeded' | 'failed' | 'cancelled'
  paused_reason: string | null
  error: string | null
  progress: { stage?: string, error_code?: string | null, question_id?: number, problems?: string[] }
  created_at: string
  finished_at: string | null
}

/** 参数槽的取值形态。 */
export type StructParamKind = 'numeric' | 'symbolic' | 'point' | 'interval' | 'expression'

/** 参数允许的取值。 */
export interface StructParamDomain {
  min?: number
  max?: number
  integer?: boolean
  values?: string[]
  exclude?: string[]
  note?: string
}

/** 参数槽:挂在一条条件或设问上的可替换值。 */
export interface StructParam {
  id: number
  ordinal: number
  element_id: number | null
  ask_id: number | null
  name: string
  slot_kind: StructParamKind
  /** 原值(与 stem_text 中 span 处的原文一致)。 */
  value: string
  span: [number, number] | null
  domain: StructParamDomain | null
  /** 老师确认过取值范围后,才能让 AI 在范围内取值。 */
  domain_confirmed: boolean
  replaceable: boolean
}

/** 保存时提交的参数(所属条目用本次提交中的下标表示)。 */
export interface StructParamInput {
  owner: 'element' | 'ask'
  owner_index: number
  name: string
  value: string
  slot_kind: StructParamKind
  span_start?: number | null
  span_end?: number | null
  domain?: StructParamDomain | null
  domain_confirmed?: boolean
  replaceable?: boolean
}

/** 最近一次变式任务。 */
export interface StructVariantJob {
  id: number
  status: 'pending' | 'running' | 'paused' | 'succeeded' | 'failed' | 'cancelled'
  paused_reason: string | null
  error: string | null
  progress: {
    stage?: string
    error_code?: string | null
    question_id?: number
    /** 参数名 → [原值, 新值]。 */
    changes?: Record<string, [string, string]>
    problems?: string[]
    /** 原选项不再适用,AI 重写了选项(需要老师核对)。 */
    options_rewritten?: boolean
  }
  created_at: string
  finished_at: string | null
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
  /** 思维量权重(方法类型使用,默认 1)。 */
  weight: number
  /** 映射的知识点(规格 §12.3 N8)。 */
  knowledge_point_ids?: number[]
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
  params?: StructParamInput[]
  groups?: StructGroupInput[]
  accept?: boolean
}

/** 审核队列的一项。 */
export interface StructReviewQueueItem {
  id: number
  target_type: StructTargetType
  target_id: number
  origin: StructOrigin
  model: string | null
  check_errors: number
  check_warnings: number
  preview: string
  created_at: string
  /** 解答审核队列:第几种解法与思维量。 */
  solution_no?: number
  thinking_load?: number | null
}

export interface StructReviewQueuePage {
  items: StructReviewQueueItem[]
  total: number
  page: number
  size: number
  pages: number
}

/** 拆解来源:站内 AI、人工修改、外部 Agent(MCP)。 */
export type StructOrigin = 'ai' | 'human' | 'agent'

/** 相关题的查找方式:类型相近 / 共享相同条件。 */
export type StructSimilarMode = 'types' | 'elements' | 'params'

/** 同结构 / 同源题。 */
export interface StructSimilarItem {
  question_id: number
  score: number
  /** mode=types:共有的类型。 */
  shared_type_ids?: number[]
  /** mode=elements:共享的条件数与内容(本题的写法)。 */
  shared_count?: number
  shared_elements?: string[]
  /** mode=params:对应的参数名(本题的写法)。 */
  shared_params?: string[]
  q_type: string
  preview: string
}

/** 学科结构化统计(首页卡片)。 */
export interface StructStats {
  total: number
  states: Record<StructState, number>
  queued: number
  unclassified: number
  /** 已采纳拆解按来源的条数。 */
  origins: Record<StructOrigin, number>
  /** 非根类型数、其中映射了知识点的类型数。 */
  types_total: number
  types_mapped: number
  /** 有思维量难度的题数。 */
  with_thinking: number
  top_types: Array<{ type_id: number, kind: StructTypeKind, path: string[], count: number }>
}

/** 元素归纳产生的候选类型(待老师确认)。 */
export interface StructTypeCandidate {
  id: number
  kind: StructTypeKind
  name: string
  definition: string | null
  /** 组内仍未归类的条目数。 */
  count: number
  /** 示例(只含当前用户可见的题目)。 */
  samples: string[]
  suggested_parent_id: number | null
  suggested_parent_path: string[]
  similar_type_id: number | null
  similar_type_path: string[]
  created_at: string
}

/** 候选列表 + 未归类条数 + 最近一次归纳任务。 */
export interface StructCandidatesView {
  items: StructTypeCandidate[]
  unclassified: Record<StructTypeKind, number>
  min_items: number
  job: { id: number, status: string, paused_reason: string | null, error: string | null, finished_at: string | null } | null
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

/** 解答步骤上的常见错误。 */
export interface SolutionMisconception {
  description: string
  source: 'distractor' | 'response'
}

/** 解答中的一步;条件 / 设问用题干拆解中的 id,前序步骤用下标。 */
export interface SolutionStep {
  id: number
  ordinal: number
  goal: string
  result: string | null
  method_type_id: number | null
  method_path: string[]
  method_hint: string | null
  weight: number
  is_key: boolean
  uses_elements: number[]
  uses_asks: number[]
  uses_steps: number[]
  answers: number[]
  misconceptions: SolutionMisconception[]
}

/** 一次解答拆解快照。 */
export interface SolutionRun {
  id: number
  question_id: number
  solution_no: number
  stem_run_id: number | null
  /** 题目改过或题干拆解被取代:需要复核。 */
  stale: boolean
  origin: StructOrigin
  model: string | null
  prompt_version: string | null
  state: StructRunState
  thinking_load: number | null
  has_reference: boolean
  check_report: StructCheckReport | null
  check_errors: number
  check_warnings: number
  created_at: string
  reviewed_at: string | null
  steps: SolutionStep[]
}

/** 一道题的解答结构全貌。 */
export interface SolutionView {
  question_id: number
  subject_id: number | null
  thinking_difficulty: number | null
  stem: {
    run_id: number
    stale: boolean
    elements: Array<{ id: number, ordinal: number, content: string }>
    asks: Array<{ id: number, ordinal: number, content: string }>
  } | null
  solutions: Array<{ solution_no: number, accepted: SolutionRun | null, draft: SolutionRun | null }>
  job: StructJob | null
}

/** 保存时提交的一步。 */
export interface SolutionStepInput {
  goal: string
  result?: string | null
  method_type_id?: number | null
  method_hint?: string | null
  is_key?: boolean
  uses_elements: number[]
  uses_asks: number[]
  uses_steps: number[]
  answers: number[]
  misconceptions: SolutionMisconception[]
}
