// 成绩录入 (Assessment / Gradebook) 域前端契约 —— 第三条纵向切片。
//
// 与后端 app/schemas/assessment.py 对齐。注意:后端分值/得分是 Decimal,
// 经 FastAPI(jsonable_encoder)序列化为 JSON **字符串**(如 "40.00")。
// 因此读取投影里的分值一律为 string;写入时后端 Decimal 兼容 number 或 string。

/** 考试生命周期状态。 */
export type ExamSessionStatus = 'draft' | 'recording' | 'locked' | 'archived'

/** 参与者出勤状态。 */
export type ExamAttendanceStatus = 'present' | 'absent'

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
// 考试题目 / 参与者 / 会话
// --------------------------------------------------------------------------- //
export interface ExamQuestion {
  id: number
  composition_node_id: string
  q_type: string
  max_score: ScoreValue
  position: number
}

export interface ExamParticipant {
  id: number
  student_id: number | null
  name: string
  student_no: string
  attendance_status: ExamAttendanceStatus
}

export interface ExamSession {
  id: number
  subject_id: number
  composition_version_id: number
  classroom_id: number
  name: string
  status: ExamSessionStatus
  revision: number
  total_score: ScoreValue
  created_at: string
  updated_at: string
}

export interface ExamSessionDetail extends ExamSession {
  questions: ExamQuestion[]
  participants: ExamParticipant[]
}

export interface ExamSessionCreateRequest {
  composition_version_id: number
  classroom_id: number
  name: string
}

// --------------------------------------------------------------------------- //
// gradebook 读取
// --------------------------------------------------------------------------- //
export interface GradebookScoreItem {
  exam_question_id: number
  score: ScoreValue | null
}

export interface GradebookRow {
  participant_id: number
  student_id: number | null
  name: string
  student_no: string
  attendance_status: ExamAttendanceStatus
  result_id: number
  revision: number
  total_score: ScoreValue | null
  is_complete: boolean
  scores: GradebookScoreItem[]
}

export interface Gradebook {
  exam_session_id: number
  status: ExamSessionStatus
  revision: number
  total_score: ScoreValue
  questions: ExamQuestion[]
  participants: GradebookRow[]
}

// --------------------------------------------------------------------------- //
// 逐题成绩保存
// --------------------------------------------------------------------------- //
export interface ScoreItemInput {
  exam_question_id: number
  // null 表示清除该题得分。
  score: ScoreInput
}

export interface ScoreSaveRequest {
  expected_revision: number
  batch_id?: string | null
  items: ScoreItemInput[]
}

/** 单参与者成绩单写后读投影。 */
export interface Result {
  result_id: number
  participant_id: number
  revision: number
  total_score: ScoreValue | null
  is_complete: boolean
  scores: GradebookScoreItem[]
}

export interface ScoreImportError {
  row: number
  field: string
  message: string
}

export interface ScoreImportPreview {
  valid: boolean
  changed_rows: number
  changed_scores: number
  unchanged_rows: number
  errors: ScoreImportError[]
}

export interface ScoreImportResult {
  batch_id: string
  updated_rows: number
  updated_scores: number
}
