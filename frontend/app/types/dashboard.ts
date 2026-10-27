export interface DashboardCountItem {
  key: string
  count: number
}

export interface DashboardOverview {
  total_questions: number
  new_questions_7d: number
  published: number
  pending: number
  stimuli: number
  compositions: number
  knowledge_points: number
  tags: number
}

export interface DashboardDistribution {
  q_type: DashboardCountItem[]
  status: DashboardCountItem[]
  difficulty: DashboardCountItem[]
  visibility: DashboardCountItem[]
}

export interface DashboardKnowledgePointCount {
  id: number
  name: string
  count: number
}

export interface DashboardKnowledgeCoverage {
  total: number
  covered: number
  top: DashboardKnowledgePointCount[]
  uncovered: DashboardKnowledgePointCount[]
  questions_without_kp: number
  questions_without_tag: number
}

export interface DashboardTrendPoint {
  date: string
  created: number
  total: number
}

export interface DashboardStats {
  subject_id: number
  overview: DashboardOverview
  distribution: DashboardDistribution
  knowledge_coverage: DashboardKnowledgeCoverage
  trend: DashboardTrendPoint[]
}

export interface DashboardContributor {
  user_id: number
  username: string
  full_name: string | null
  avatar_url: string | null
  created: number
  reviewed: number
}

export interface DashboardContributors {
  subject_id: number
  days: number
  items: DashboardContributor[]
}
