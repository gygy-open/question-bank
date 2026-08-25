// 组稿 (Composition) 领域类型 —— 前端第一阶段。
// 与后端 app/schemas/composition.py 严格对齐。

import type { RichDoc, RichDocNode } from './richContent'
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
}

// 折叠成树后的目录节点。
export interface CompositionFolderNode extends CompositionFolder {
  children: CompositionFolderNode[]
}

// --- Block 判别联合（与后端 CompositionBlockType 一一对应） --- //

export type CompositionBlockType =
  | 'rich_text'
  | 'heading'
  | 'question'
  | 'page_break'
  | 'answer_summary'

export type HeadingLevel = 1 | 2 | 3 | 4

export interface HeadingProps {
  level: HeadingLevel
}

export type AnswerSummaryMode = 'all' | 'before'

export interface AnswerSummaryProps {
  mode: AnswerSummaryMode
}

interface CompositionBlockCommon {
  id: number
  composition_id: number
  sequence: number
  schema_version: number
}

export interface RichTextBlock extends CompositionBlockCommon {
  block_type: 'rich_text'
  content: RichDocNode
  props: null
  question_id: null
  question_revision: null
}

export interface HeadingBlock extends CompositionBlockCommon {
  block_type: 'heading'
  content: RichDocNode
  props: HeadingProps
  question_id: null
  question_revision: null
}

export interface QuestionBlock extends CompositionBlockCommon {
  block_type: 'question'
  content: null
  props: null
  question_id: number
  question_revision: number
}

export interface PageBreakBlock extends CompositionBlockCommon {
  block_type: 'page_break'
  content: null
  props: null
  question_id: null
  question_revision: null
}

export interface AnswerSummaryBlock extends CompositionBlockCommon {
  block_type: 'answer_summary'
  content: null
  props: AnswerSummaryProps
  question_id: null
  question_revision: null
}

/** 服务端返回的 block 判别联合（GET detail / replace 响应共用）。 */
export type CompositionBlock =
  | RichTextBlock
  | HeadingBlock
  | QuestionBlock
  | PageBreakBlock
  | AnswerSummaryBlock

/** GET composition detail：元数据 + 有序 blocks。 */
export interface CompositionDetail extends Composition {
  blocks: CompositionBlock[]
}

// --- 批量替换请求/响应契约 --- //
// 每个 item 携带 id（已有 block）或 temp_id（新 block），二者恰有其一；顺序即 sequence。
// question block 的 question_revision 由服务端钉住，客户端传值被忽略。

export interface CompositionBlockReplaceItem {
  id?: number
  temp_id?: string
  block_type: CompositionBlockType
  content?: RichDocNode | null
  props?: Record<string, unknown> | null
  schema_version?: number
  question_id?: number | null
  question_revision?: number | null
}

export interface CompositionBlocksReplaceRequest {
  expected_revision: number
  batch_id?: string
  blocks: CompositionBlockReplaceItem[]
}

export interface CompositionBlocksReplaceResponse {
  revision: number
  // temp_id → 新建 block 的真实服务端 id。
  id_map: Record<string, number>
  blocks: CompositionBlock[]
}

// --- 定稿 (Version) 契约 --- //
// 与后端 CompositionVersionCreateRequest / CompositionVersionSummary /
// CompositionVersionRead 及 snapshot v1 构件严格对齐。

/** 定稿请求体：expected_revision 乐观校验（不修改 revision），label 可选备注。 */
export interface CompositionVersionCreatePayload {
  expected_revision: number
  label?: string | null
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

/**
 * 定稿时冻结的题目内容投影（snapshot v1）。
 * 只含可发布内容，排除关系（标签/知识点/创建人）、权限与审核字段。
 */
export interface QuestionSnapshot {
  id: number
  content_revision: number
  content_schema_version: number
  q_type: QuestionType
  content: RichDoc
  options: OptionSpec[] | null
  answer: AnswerSpec | null
  thinking: RichDoc
  analysis: RichDoc
  summary: RichDoc
  difficulty: number
  source: string | null
}

// --- snapshot block 判别联合（只读，仅消费快照，不查询当前题库） --- //

export interface SnapshotRichTextBlock {
  block_type: 'rich_text'
  content: RichDocNode
}

export interface SnapshotHeadingBlock {
  block_type: 'heading'
  content: RichDocNode
  props: { level: HeadingLevel }
}

export interface SnapshotQuestionBlock {
  block_type: 'question'
  question_id: number
  question_revision: number
  // 定稿时题目已删除则为 null（历史上不可再恢复内容）。
  question: QuestionSnapshot | null
}

export interface SnapshotPageBreakBlock {
  block_type: 'page_break'
}

export interface SnapshotAnswerSummaryBlock {
  block_type: 'answer_summary'
  props: { mode: AnswerSummaryMode }
  // 服务端按 sequence 去重保序解析出的 question_id 列表（all/before 语义在服务端固化）。
  resolved_question_ids: number[]
}

export type SnapshotBlock =
  | SnapshotRichTextBlock
  | SnapshotHeadingBlock
  | SnapshotQuestionBlock
  | SnapshotPageBreakBlock
  | SnapshotAnswerSummaryBlock

/** snapshot v1：顶层元数据 + 按 sequence 的 block 投影。 */
export interface CompositionSnapshotV1 {
  schema_version: 1
  composition_id: number
  source_revision: number
  title: string
  subject_id: number
  finalized_at: string
  blocks: SnapshotBlock[]
}

/** GET version detail：版本元数据 + 不可变 snapshot。 */
export interface CompositionVersionDetail {
  id: number
  composition_id: number
  version_no: number
  source_revision: number
  title: string
  subject_id: number
  snapshot: CompositionSnapshotV1
  label: string | null
  finalized_at: string
  finalized_by: number
}
