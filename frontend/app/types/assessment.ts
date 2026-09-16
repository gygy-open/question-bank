// 通用评测 (Assessment / Gradebook) 域前端契约 —— 评测重构后的数据层。
//
// 与后端 app/schemas/assessment.py 对齐。注意:后端分值/得分是 Decimal,
// 经 FastAPI(jsonable_encoder)序列化为 JSON **字符串**(如 "40.00")。
// 因此读取投影里的分值一律为 string;写入时后端 Decimal 兼容 number 或 string。

/** 评测身份生命周期。 */
export type AssessmentStatus = 'active' | 'archived'

/** 投放状态。线下默认 closed。 */
export type DeliveryStatus = 'draft' | 'open' | 'closed'

/** 评分状态。finalized 之后只读。 */
export type GradingStatus = 'not_started' | 'in_progress' | 'finalized'

/** 参与者出勤状态。 */
export type AttendanceStatus = 'present' | 'absent' | 'excused'

/** 参与状态。 */
export type ParticipationStatus = 'invited' | 'active' | 'completed' | 'withdrawn'

/** attempt 投放模式。 */
export type AttemptMode = 'offline' | 'online'

/** attempt 状态。 */
export type AttemptStatus =
  | 'not_started'
  | 'in_progress'
  | 'submitted'
  | 'grading'
  | 'graded'
  | 'void'

/** 评分结果分类。 */
export type GradeOutcome = 'correct' | 'partial' | 'incorrect' | 'unscored'

/** 评分方式。 */
export type GradingMethod = 'manual' | 'imported' | 'automatic'

/** 读取投影里的分值(后端 Decimal 序列化为字符串)。 */
export type ScoreValue = string

/** 写入分值:后端 Decimal 兼容 number / string;null 表示清除该题得分。 */
export type ScoreInput = number | string | null

// --------------------------------------------------------------------------- //
// 学生 / 班级名册
// --------------------------------------------------------------------------- //
export interface Student {
  id: number
  subject_id: number
  user_id: number | null
  student_no: string
  name: string
}

export interface Classroom {
  id: number
  subject_id: number
  name: string
}

export interface StudentCreateRequest {
  student_no: string
  name: string
  user_id?: number | null
}

export interface StudentPage {
  items: Student[]
  total: number
  page: number
  page_size: number
}

export interface ClassroomCreateRequest {
  name: string
}

export interface ClassroomMembersReplaceRequest {
  student_ids: number[]
}

// --------------------------------------------------------------------------- //
// 评测身份 / 版本 / 条目
// --------------------------------------------------------------------------- //
export interface Assessment {
  id: number
  subject_id: number
  title: string
  description: string | null
  status: AssessmentStatus | string
  created_at: string
  updated_at: string
}

export interface AssessmentVersion {
  id: number
  assessment_id: number
  version_no: number
  composition_version_id: number | null
  source_type: string
  total_score: ScoreValue | null
  item_count: number | null
  created_at: string
}

/** 公开条目投影:不含私有 scoring_spec。 */
export interface AssessmentItem {
  id: number
  item_key: string
  position: number
  item_type: string
  max_score: ScoreValue
  parent_item_id: number | null
  source_question_id: number | null
  source_question_revision: number | null
}

export interface AssessmentDetail extends Assessment {
  versions: AssessmentVersion[]
  current_items: AssessmentItem[]
}

export interface AssessmentCreateRequest {
  title: string
  composition_version_id: number
  classroom_id: number
  session_name?: string | null
}

// --------------------------------------------------------------------------- //
// 投放 session / 参与 / attempt
// --------------------------------------------------------------------------- //
export interface AttemptSummary {
  attempt_id: number
  attempt_no: number
  mode: AttemptMode | string
  status: AttemptStatus | string
  revision: number
  total_score: ScoreValue | null
  max_score: ScoreValue | null
  answered_count: number
  graded_count: number
}

export interface Participation {
  id: number
  participant_key: string
  student_id: number | null
  user_id: number | null
  display_name: string | null
  identifier: string | null
  attendance_status: AttendanceStatus | string
  status: ParticipationStatus | string
  attempts: AttemptSummary[]
}

export interface Session {
  id: number
  assessment_id: number
  assessment_title: string | null
  version_id: number
  subject_id: number
  name: string
  delivery_status: DeliveryStatus | string
  grading_status: GradingStatus | string
  revision: number
  created_at: string
  updated_at: string
}

export interface SessionDetail {
  id: number
  assessment_id: number
  assessment_title: string | null
  version_id: number
  version_no: number
  subject_id: number
  name: string
  delivery_status: DeliveryStatus | string
  grading_status: GradingStatus | string
  opens_at: string | null
  closes_at: string | null
  attempt_limit: number | null
  revision: number
  created_at: string
  updated_at: string
  total_score: ScoreValue | null
  item_count: number | null
  items: AssessmentItem[]
  participants: Participation[]
}

// --------------------------------------------------------------------------- //
// 追加式评分
// --------------------------------------------------------------------------- //
export interface GradeItemInput {
  item_id: number
  // null 表示清除该题得分。
  score?: ScoreInput
  outcome?: GradeOutcome | string | null
  grading_method?: GradingMethod | string | null
  feedback?: unknown
}

export interface GradeAppendRequest {
  expected_revision: number
  batch_id?: string | null
  items: GradeItemInput[]
}

export interface AttemptGradeRow {
  item_id: number
  item_key: string
  max_score: ScoreValue
  response_id: number | null
  score: ScoreValue | null
  outcome: GradeOutcome | string | null
  grade_revision: number
  status: string
}

export interface AttemptGradeResult {
  attempt_id: number
  participation_id: number
  attempt_no: number
  status: AttemptStatus | string
  revision: number
  total_score: ScoreValue | null
  max_score: ScoreValue | null
  answered_count: number
  graded_count: number
  grades: AttemptGradeRow[]
}

// --------------------------------------------------------------------------- //
// gradebook 读取(分页)
// --------------------------------------------------------------------------- //
export interface GradebookScore {
  item_id: number
  score: ScoreValue | null
  outcome: GradeOutcome | string | null
}

export interface GradebookRow {
  participation_id: number
  participant_key: string
  display_name: string | null
  identifier: string | null
  attendance_status: AttendanceStatus | string
  participation_status: ParticipationStatus | string
  attempt_id: number | null
  attempt_revision: number
  attempt_status: AttemptStatus | string | null
  total_score: ScoreValue | null
  graded_count: number
  scores: GradebookScore[]
}

export interface Gradebook {
  session_id: number
  grading_status: GradingStatus | string
  delivery_status: DeliveryStatus | string
  revision: number
  total_score: ScoreValue | null
  item_count: number
  items: AssessmentItem[]
  participants: GradebookRow[]
  page: number
  page_size: number
  total: number
}

// --------------------------------------------------------------------------- //
// item 统计
// --------------------------------------------------------------------------- //
export interface ItemStatistic {
  item_id: number
  item_key: string
  position: number
  max_score: ScoreValue
  graded_count: number
  average_score: ScoreValue | null
  min_score: ScoreValue | null
  max_score_awarded: ScoreValue | null
  full_marks_count: number
  incorrect_count: number
  // 失分率:未拿满分的比例(相对已评分作答);无评分时为 null。
  error_rate: ScoreValue | null
}

export interface ItemStatistics {
  session_id: number
  grading_status: GradingStatus | string
  participation_count: number
  items: ItemStatistic[]
}

// --------------------------------------------------------------------------- //
// 成绩册 Excel 导入
// --------------------------------------------------------------------------- //
export interface ScoreImportError {
  row: number
  field: string
  message: string
}

export interface ScoreImportPreview {
  session_id: number
  valid: boolean
  total_rows: number
  changed_rows: number
  changed_scores: number
  unchanged_rows: number
  errors: ScoreImportError[]
}

export interface ScoreImportResult {
  session_id: number
  batch_id: string | null
  changed_rows: number
  changed_scores: number
  unchanged_rows: number
  applied_attempts: number
  // 幂等重放命中(相同 batch_id + 同文件)时为 true,表示未再次写库。
  replayed: boolean
}
