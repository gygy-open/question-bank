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
  category: string
  color: string
  subject_id: number
}

export interface TagCategory {
  id: number
  name: string
  slug: string
  sort_order: number
  is_active: boolean
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
  content: string
  options?: any[]
  answer: string
  thinking?: string
  analysis?: string
  summary?: string
  q_type: string
  status: 'draft' | 'pending' | 'published' | 'archived'
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

export interface ImportItem {
  id: string
  selected: boolean
  content: string
  q_type: 'single_choice' | 'multiple_choice' | 'true_false' | 'fill_in_the_blank' | 'free_response'
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
  content: string
  q_type: string
  difficulty: number
  options?: { label: string; content: string }[] | null
  answer?: string | null
  thinking?: string | null
  analysis?: string | null
  summary?: string | null
  source?: string | null
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

// --- Composition (Block Canvas) ---

export type BlockType = 'heading' | 'text' | 'question' | 'page_break'

export type CompositionScope = 'team' | 'personal'

export type AnswerPosition = 'after_question' | 'end_of_paper' | 'hidden'

/** 内容字段落位区域 (开放枚举)。 */
export type DisplayRegion = 'inline' | 'appendix' | 'hidden'

/** 可配置显示的字段。 */
export type DisplayField = 'answer' | 'analysis' | 'explanation' | 'summary' | 'source'

/** 显示策略: 文档级默认与题块级覆盖共用同一结构。 */
export interface DisplayPolicy {
  v?: number
  fields?: Partial<Record<DisplayField, { region: DisplayRegion }>>
}

/** 题号编号策略 (文档级默认, 无题块级覆盖)。 */
export interface NumberingPolicy {
  auto?: boolean                    // 默认 true; 关闭则全文档不显示题号
  scope?: 'section' | 'document' | 'outline'  // 'section' 遇标题重置; 'document' 全文连续; 'outline' 按 H2~H4 嵌套生成 "2.1.3" 式题号
}

/** 赋分策略 (文档级默认, 无题块级覆盖)。 */
export interface ScoringPolicy {
  enabled?: boolean  // 默认 true; 关闭则隐藏分值输入/展示, 且导出时不打印分值 (不清除已录入的分数)
}

/** 文档级设置 (存于 meta_data)。 */
export interface CompositionSettings {
  display?: DisplayPolicy
  numbering?: NumberingPolicy
  scoring?: ScoringPolicy
}


export interface Folder {
  id: number
  name: string
  parent_id?: number | null
  scope: CompositionScope
  subject_id: number
  owner_id: number
  sequence?: number
}

export interface CompositionBlock {
  id: number
  block_type: BlockType
  sequence: number
  content?: Record<string, any> | null
  ref_question_id?: number | null
  question?: QuestionBrief | null
}

export interface Composition {
  id: number
  title: string
  description?: string | null
  status: 'draft' | 'published' | 'archived'
  is_template: boolean
  difficulty?: number | null
  meta_data?: CompositionSettings | null
  folder_id: number
  subject_id?: number | null
  scope?: CompositionScope | null
  owner_id: number
  created_at: string
  updated_at: string
  block_count: number
}

/** 新建起点: 系统预置模板 (source=system) 或自定义模板 (source=custom)。 */
export interface TemplateItem {
  source: 'system' | 'custom'
  key?: string | null
  id?: number | null
  label: string
  icon?: string | null
  description?: string | null
  scope?: CompositionScope | null
}

export interface CompositionDetail extends Composition {
  blocks: CompositionBlock[]
}

/** Block payload for saving (PUT /compositions/:id/blocks). */
export interface BlockWrite {
  block_type: BlockType
  content?: Record<string, any> | null
  ref_question_id?: number | null
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
