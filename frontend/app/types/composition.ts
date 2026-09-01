// 组稿 (Composition) 领域类型 —— CompositionNode AST 阶段。
// 与后端 app/schemas/composition.py 严格对齐（node 契约 + snapshot v2）。

import type { RichDocNode } from './richContent'
import type { AnswerSpec, OptionSpec, QuestionType } from './question'

export type CompositionScope = 'shared' | 'personal'

export type CompositionStatus = 'draft' | 'archived'

export interface CompositionFolder {
  id: number
  name: string
  scope_type: CompositionScope
  owner_id: number | null
  subject_id: number
  parent_id: number | null
  created_at: string
  updated_at: string
}

export interface Composition {
  id: number
  title: string
  description: string | null
  status: CompositionStatus
  revision: number
  numbering_enabled: boolean
  scoring_enabled: boolean
  question_display: Record<AnswerFieldKey, boolean>
  scope_type: CompositionScope
  owner_id: number | null
  subject_id: number
  folder_id: number | null
  created_at: string
  updated_at: string
  deleted_at: string | null
}

// --- 请求体（scope/subject/owner 由路径与鉴权强制，前端绝不传递 owner） --- //

export interface FolderCreatePayload {
  name: string
  parent_id?: number | null
}

export interface FolderUpdatePayload {
  name?: string
  // 显式传 null 表示移动到根目录；后端用 model_fields_set 区分未提供与置空。
  parent_id?: number | null
}

export interface CompositionCreatePayload {
  title: string
  description?: string | null
  folder_id?: number | null
}

export interface CompositionMetaUpdatePayload {
  expected_revision: number
  title?: string
  description?: string | null
  status?: CompositionStatus
  // 显式传 null 表示移出目录（根）。
  folder_id?: number | null
  numbering_enabled?: boolean
  scoring_enabled?: boolean
  question_display?: Record<AnswerFieldKey, boolean>
}

// 折叠成树后的目录节点。
export interface CompositionFolderNode extends CompositionFolder {
  children: CompositionFolderNode[]
}

// --- Node 判别联合（与后端 CompositionNode* 对齐） --- //

export type CompositionNodeKind = 'block' | 'module' | 'reference'

export type CompositionNodeType =
  | 'rich_text'
  | 'heading'
  | 'question'
  | 'page_break'
  | 'answer_space'
  | 'question_details'
  | 'answer_item'

// module 子节点唯一 slot 名（与后端 BODY_SLOT 对齐）。
export const BODY_SLOT = 'body'

export type HeadingLevel = 1 | 2 | 3 | 4

export interface HeadingProps {
  level: HeadingLevel
}

/** 作答空间样式：纯空白或答题横线。 */
export type AnswerSpaceStyle = 'blank' | 'lined'

/** answer_space 节点属性：按行数控高 + 样式。 */
export interface AnswerSpaceProps {
  lines: number
  style: AnswerSpaceStyle
}

/** 选项排版：auto=按内容长度自适应列数，或固定 1/2/4 列。缺省视为 auto。 */
export type OptionLayout = 'auto' | 1 | 2 | 4

/** question 节点可选题号（纠数字或 1.1 形式），存于 node.props。 */
export interface QuestionProps {
  number?: string | null
  // 题目级字段显隐覆盖：true=显示、false=隐藏、缺省/null=继承全局。
  show?: Partial<Record<AnswerFieldKey, boolean | null>>
  // 选项排版覆盖（每卷生效）；缺省/'auto' 由内容长度自适应。
  optionLayout?: OptionLayout
  // 题目分值（0~1000，允许 0.5 步进小数）；仅在组稿 scoring_enabled 为真时展示/可编辑。
  score?: number | null
}

// question_details / answer_item 覆盖涉及的四个可发布字段。
export type AnswerFieldKey = 'answer' | 'thinking' | 'analysis' | 'summary'

export const ANSWER_FIELD_KEYS: readonly AnswerFieldKey[] = [
  'answer',
  'thinking',
  'analysis',
  'summary',
]

export type DetailScope = 'before' | 'all'

/** question_details module 属性：范围 + 四字段全局开关。 */
export interface QuestionDetailsProps {
  scope: DetailScope
  fields: Record<AnswerFieldKey, boolean>
}

/** answer_item 覆盖：null=继承 module 全局开关，true/false=显式显示/隐藏。 */
export type AnswerItemOverride = boolean | null

export interface AnswerItemProps {
  included: boolean
  overrides: Record<AnswerFieldKey, AnswerItemOverride>
}

/**
 * 冻结在 question 节点上的题目内容快照（不含 id/revision）。
 * 与后端 QuestionContentSnapshot 严格对齐；id 由 question_id、revision 由 question_revision 承载。
 */
export interface QuestionContentSnapshot {
  content_schema_version: number
  q_type: QuestionType
  content: RichDocNode | null
  options: OptionSpec[] | null
  answer: AnswerSpec | null
  thinking: RichDocNode | null
  analysis: RichDocNode | null
  summary: RichDocNode | null
  difficulty: number
  source: string | null
}

interface CompositionNodeCommon {
  id: string
  composition_id: number
  parent_id: string | null
  slot: string | null
  position: number
  schema_version: number
}

export interface RichTextNode extends CompositionNodeCommon {
  node_kind: 'block'
  node_type: 'rich_text'
  content: RichDocNode
  props: null
  question_id: null
  question_revision: null
  source_question_node_id: null
  anchor_before_node_id: string | null
}

export interface HeadingNode extends CompositionNodeCommon {
  node_kind: 'block'
  node_type: 'heading'
  content: RichDocNode
  props: HeadingProps
  question_id: null
  question_revision: null
  source_question_node_id: null
  anchor_before_node_id: string | null
}

export interface QuestionNode extends CompositionNodeCommon {
  node_kind: 'block'
  node_type: 'question'
  content: QuestionContentSnapshot | null
  props: null
  question_id: number
  question_revision: number
  source_question_node_id: null
  anchor_before_node_id: null
}

export interface PageBreakNode extends CompositionNodeCommon {
  node_kind: 'block'
  node_type: 'page_break'
  content: null
  props: null
  question_id: null
  question_revision: null
  source_question_node_id: null
  anchor_before_node_id: null
}

export interface AnswerSpaceNode extends CompositionNodeCommon {
  node_kind: 'block'
  node_type: 'answer_space'
  content: null
  props: AnswerSpaceProps
  question_id: null
  question_revision: null
  source_question_node_id: null
  anchor_before_node_id: null
}

export interface QuestionDetailsNode extends CompositionNodeCommon {
  node_kind: 'module'
  node_type: 'question_details'
  content: null
  props: QuestionDetailsProps
  question_id: null
  question_revision: null
  source_question_node_id: null
  anchor_before_node_id: null
}

export interface AnswerItemNode extends CompositionNodeCommon {
  node_kind: 'reference'
  node_type: 'answer_item'
  content: null
  props: AnswerItemProps
  question_id: null
  question_revision: null
  source_question_node_id: string
  anchor_before_node_id: null
}

/** 服务端返回的 node 判别联合（GET detail / replace / sync 响应共用）。 */
export type CompositionNode =
  | RichTextNode
  | HeadingNode
  | QuestionNode
  | PageBreakNode
  | AnswerSpaceNode
  | QuestionDetailsNode
  | AnswerItemNode

/** GET composition detail：元数据 + 有序 nodes（含 module 子节点）。 */
export interface CompositionDetail extends Composition {
  nodes: CompositionNode[]
}

// --- 整体替换请求/响应契约（AST 契约） --- //
// 每个 node 携带客户端生成的 UUID id；position 不由客户端传入，由服务端按 (parent, slot) 顺序规范化。
// question 节点的 content / question_revision 由服务端冻结/钉住，客户端传值被忽略。

export interface CompositionNodeInput {
  id: string
  parent_id?: string | null
  slot?: string | null
  node_kind: CompositionNodeKind
  node_type: CompositionNodeType
  content?: RichDocNode | null
  props?: Record<string, unknown> | null
  schema_version?: number
  question_id?: number | null
  source_question_node_id?: string | null
  anchor_before_node_id?: string | null
}

export interface CompositionNodesReplaceRequest {
  expected_revision: number
  batch_id?: string
  nodes: CompositionNodeInput[]
}

export interface CompositionNodesReplaceResponse {
  revision: number
  nodes: CompositionNode[]
}

// --- Question node 版本状态 / 同步契约 --- //

/** 稿件内某 question_id 的实时状态（仅状态，不含题目内容）。 */
export interface QuestionRevisionStatus {
  question_id: number
  // available=false（软删/缺失）时为 null。
  current_revision: number | null
  available: boolean
}

/** 同步请求：expected_revision 乐观校验；node_ids 唯一非空（"同步此题"传一个，"同步全部"传全部）。 */
export interface CompositionQuestionNodesSyncRequest {
  expected_revision: number
  node_ids: string[]
}

/** 同步响应：自增后的 revision + 刷新后的完整 node 序列。 */
export interface CompositionQuestionNodesSyncResponse {
  revision: number
  nodes: CompositionNode[]
}

// --- 定稿 (Version) 契约 --- //

/** 定稿请求体：expected_revision 乐观校验（不修改 revision），label 可选备注。 */
export interface CompositionVersionCreatePayload {
  expected_revision: number
  label?: string | null
}

/** 版本导出格式：与后端 app.schemas.paper.OutputFormat 对齐。 */
export type CompositionExportFormat = 'docx' | 'latex'

/** 版本导出请求体：title 可选覆盖导出文件里的标题。 */
export interface CompositionExportPayload {
  format: CompositionExportFormat
  title?: string
}

/** 版本列表项：不含 snapshot，避免列表响应携带整稿快照。 */
export interface CompositionVersionSummary {
  id: number
  composition_id: number
  version_no: number
  source_revision: number
  title: string
  subject_id: number
  label: string | null
  finalized_at: string
  finalized_by: number
}

// --- 时间线 (Event) 契约 --- //

/** 与后端 CompositionEvent.event_type 对齐的已知取值；后端仍可能新增，故不做穷尽联合校验。 */
export type CompositionEventType =
  | 'created'
  | 'updated'
  | 'moved'
  | 'deleted'
  | 'restored'
  | 'nodes_replaced'
  | 'question_nodes_synced'
  | 'finalized'

export interface CompositionEventActor {
  id: number
  username: string
  full_name?: string | null
}

export interface CompositionEvent {
  id: number
  composition_id: number
  composition_revision: number
  event_type: CompositionEventType
  target_type: string | null
  target_id: string | null
  summary: string
  payload: Record<string, unknown> | null
  batch_id: string | null
  actor_id: number
  actor: CompositionEventActor | null
  created_at: string
}

/** 时间线游标分页响应：has_more=true 时可用最后一条 id 作为下一页 before_id。 */
export interface CompositionEventPage {
  items: CompositionEvent[]
  has_more: boolean
}


/**
 * 定稿时冻结的题目内容投影（snapshot v2 内 question 节点携带）。
 * 只含可发布内容，排除关系（标签/知识点/创建人）、权限与审核字段。
 */
export interface QuestionSnapshot {
  id: number
  content_revision: number
  content_schema_version: number
  q_type: QuestionType
  content: RichDocNode | null
  options: OptionSpec[] | null
  answer: AnswerSpec | null
  thinking: RichDocNode | null
  analysis: RichDocNode | null
  summary: RichDocNode | null
  difficulty: number
  source: string | null
}

// --- snapshot v2 node 判别联合（只读，仅消费快照，不查询当前题库） --- //

interface SnapshotNodeCommon {
  id: string
  parent_id: string | null
  slot: string | null
  position: number
  schema_version: number
  anchor_before_node_id?: string
}

export interface SnapshotRichTextNode extends SnapshotNodeCommon {
  node_kind: 'block'
  node_type: 'rich_text'
  content: RichDocNode
}

export interface SnapshotHeadingNode extends SnapshotNodeCommon {
  node_kind: 'block'
  node_type: 'heading'
  content: RichDocNode
  props: HeadingProps
}

export interface SnapshotQuestionNode extends SnapshotNodeCommon {
  node_kind: 'block'
  node_type: 'question'
  question_id: number
  question_revision: number
  question: QuestionSnapshot
  // 冻结的表现层覆盖（选项排版等）；旧快照无此字段时按缺省处理。
  props?: QuestionProps | null
}

export interface SnapshotPageBreakNode extends SnapshotNodeCommon {
  node_kind: 'block'
  node_type: 'page_break'
}

export interface SnapshotAnswerSpaceNode extends SnapshotNodeCommon {
  node_kind: 'block'
  node_type: 'answer_space'
  props: AnswerSpaceProps
}

export interface SnapshotQuestionDetailsNode extends SnapshotNodeCommon {
  node_kind: 'module'
  node_type: 'question_details'
  props: QuestionDetailsProps
}

export interface SnapshotAnswerItemNode extends SnapshotNodeCommon {
  node_kind: 'reference'
  node_type: 'answer_item'
  source_question_node_id: string
  props: AnswerItemProps
}

export type SnapshotNode =
  | SnapshotRichTextNode
  | SnapshotHeadingNode
  | SnapshotQuestionNode
  | SnapshotPageBreakNode
  | SnapshotAnswerSpaceNode
  | SnapshotQuestionDetailsNode
  | SnapshotAnswerItemNode

/** snapshot v2：顶层元数据 + 前序展平的规范化节点（root 按 position，module 子节点紧随其后）。 */
export interface CompositionSnapshotV2 {
  schema_version: 2
  composition_id: number
  source_revision: number
  title: string
  subject_id: number
  finalized_at: string
  // 定稿时刻冻结的显示默认值；旧快照（功能上线前定稿）没有这三个字段，消费方需按 false/全 false 兜底。
  numbering_enabled?: boolean
  scoring_enabled?: boolean
  question_display?: Record<AnswerFieldKey, boolean>
  nodes: SnapshotNode[]
}

/** GET version detail：版本元数据 + 不可变 snapshot。 */
export interface CompositionVersionDetail {
  id: number
  composition_id: number
  version_no: number
  source_revision: number
  title: string
  subject_id: number
  snapshot: CompositionSnapshotV2
  label: string | null
  finalized_at: string
  finalized_by: number
}
