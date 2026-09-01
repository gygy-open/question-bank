export type {
  RichDoc,
  RichDocNode,
  RichNode,
  RichMark,
} from './richContent'
export type {
  QuestionType,
  QuestionStatus,
  OptionSpec,
  AnswerSpec,
  SingleChoiceAnswer,
  MultipleChoiceAnswer,
  TrueFalseAnswer,
  FillBlankAnswer,
  FreeResponseAnswer,
  LegacyUnresolvedAnswer,
  Blank,
} from './question'
export type {
  CompositionScope,
  CompositionStatus,
  CompositionFolder,
  Composition,
  FolderCreatePayload,
  FolderUpdatePayload,
  CompositionCreatePayload,
  CompositionMetaUpdatePayload,
  CompositionFolderNode,
  CompositionNodeKind,
  CompositionNodeType,
  HeadingLevel,
  HeadingProps,
  AnswerFieldKey,
  DetailScope,
  QuestionDetailsProps,
  AnswerItemOverride,
  AnswerItemProps,
  QuestionContentSnapshot,
  RichTextNode,
  HeadingNode,
  QuestionNode,
  PageBreakNode,
  QuestionDetailsNode,
  AnswerItemNode,
  CompositionNode,
  CompositionDetail,
  CompositionNodeInput,
  CompositionNodesReplaceRequest,
  CompositionNodesReplaceResponse,
  QuestionRevisionStatus,
  CompositionQuestionNodesSyncRequest,
  CompositionQuestionNodesSyncResponse,
  CompositionVersionCreatePayload,
  CompositionVersionSummary,
  CompositionVersionDetail,
  CompositionExportFormat,
  CompositionExportPayload,
  CompositionSnapshotV2,
  QuestionSnapshot,
  SnapshotNode,
  SnapshotRichTextNode,
  SnapshotHeadingNode,
  SnapshotQuestionNode,
  SnapshotPageBreakNode,
  SnapshotQuestionDetailsNode,
  SnapshotAnswerItemNode,
  CompositionEventType,
  CompositionEventActor,
  CompositionEvent,
  CompositionEventPage,
} from './composition'
export {
  ANSWER_FIELD_KEYS,
  BODY_SLOT,
} from './composition'

import type { RichDoc } from './richContent'
import type {
  QuestionType,
  QuestionStatus,
  OptionSpec,
  AnswerSpec,
} from './question'

export interface Subject {
  id: number
  name: string
  slug: string
  description?: string
  required_review_count: number
  created_at: string
}

export interface SubjectCreate {
  name: string
  slug: string
  description?: string
  required_review_count?: number
}

export interface KnowledgePoint {
  id: number
  name: string
  slug: string
  subject_id: number
  parent_id?: number
}

export interface VectorStatus {
  embedding_configured: boolean
  db_count: number
  vector_count: number
  needs_reindex: boolean
  reason: string
}

export interface ReindexResult {
  status: string
  reindexed: number
  duration: number
}

export interface KPImportRowError {
  row: number
  message: string
}

export interface KPImportResult {
  status: 'success' | 'partial' | 'failed'
  subject_name?: string
  mode: string
  created: number
  skipped: number
  failed: number
  total: number
  duration: number
  vector_synced: boolean
  errors: KPImportRowError[]
}

export interface KPImportPreflight {
  subject_id: number
  subject_name: string
  existing_count: number
  affected_questions: number
}

export interface UserImportRowError {
  row: number
  message: string
}

export interface UserImportResult {
  status: 'success' | 'partial' | 'failed'
  created: number
  failed: number
  total: number
  errors: UserImportRowError[]
}

export interface Tag {
  id: number
  name: string
  category_id: number | null
  color: string
  subject_id: number
}

export interface TagCategory {
  id: number
  name: string
  sort_order: number
  is_active: boolean
}

export interface TagPage {
  items: Tag[]
  total: number
  page: number
  size: number
  pages: number
}

export interface User {
  id: number
  username: string
  full_name?: string
  avatar_url?: string
  is_superuser?: boolean
}

export interface ActivityLog {
  id: number
  user_id?: number
  action: string
  resource_type?: string
  resource_id?: number
  details?: any
  created_at: string
  user?: User
}

export interface ImportTask {
  id: number
  description?: string
  source: string
  file_path: string
  original_filename: string
  file_type: string
  mode: string
  status: string
  error_message?: string
  created_at: string
}

export interface Question {
  id: number
  content_revision: number
  content_schema_version: number
  content: RichDoc
  options?: OptionSpec[] | null
  answer?: AnswerSpec | null
  thinking?: RichDoc
  analysis?: RichDoc
  summary?: RichDoc
  q_type: QuestionType
  status: QuestionStatus
  difficulty: number
  knowledge_points: KnowledgePoint[]
  tags: Tag[]
  created_at: string
  updated_at: string
  import_task_id?: number
  import_task?: ImportTask
  subject_id?: number
  review_count: number
  source?: string
  creator?: User
  updater?: User
  review_logs?: ActivityLog[]
  subject?: Subject
  parent_id?: number
  parent?: Question
  children?: Question[]
}

// 导入工作台条目：保持旧的 Markdown 字符串格式（题干/选项/答案均为字符串），
// 由旧 TiptapEditor/MarkdownPreview 服务，落库前才转换为 v2 RichDoc。
export interface ImportItem {
  id: string
  selected: boolean
  content: string
  q_type: QuestionType
  options: { label: string, content: string }[]
  answer: string
  thinking?: string
  analysis: string
  difficulty: number
  knowledge_point_ids: number[]
  subject_id?: number
  ai_suggested_tags?: Record<string, string[]>
  warnings?: string[]
}

export interface QuestionPage {
  items: Question[]
  total: number
  page: number
  size: number
  pages: number
}

export interface QuestionBrief {
  id: number
  content: RichDoc
  q_type: QuestionType
  difficulty: number
  options?: OptionSpec[] | null
  answer?: AnswerSpec | null
  thinking?: RichDoc
  analysis?: RichDoc
  summary?: RichDoc
}

export interface PaperItem {
  id: number
  question_id: number
  sequence: number
  section_title?: string | null
  score?: number | null
  question?: QuestionBrief | null
}

export interface Paper {
  id: number
  title: string
  description?: string | null
  status: 'draft' | 'archived'
  subject_id?: number | null
  owner_id: number
  created_at: string
  updated_at: string
  question_count: number
}

export interface PaperDetail extends Paper {
  items: PaperItem[]
}


export interface User {
  id: number
  username: string
  full_name?: string
  avatar_url?: string
  is_active: boolean
  is_superuser: boolean
  subject_id?: number
  last_active_subject_id?: number
}

export interface LoginRequest {
  username: string
  password: string
}

export interface UserUpdatePassword {
  current_password: string
  new_password: string
}
