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

export interface Tag {
  id: number
  name: string
  category: string
  color: string
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
}

export interface QuestionPage {
  items: Question[]
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
  is_active: boolean
  is_superuser: boolean
}

export interface LoginRequest {
  username: string
  password: string
}

export interface UserUpdatePassword {
  current_password: string
  new_password: string
}
