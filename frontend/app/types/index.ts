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
