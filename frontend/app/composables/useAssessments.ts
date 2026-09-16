import type {
  Assessment,
  AssessmentCreateRequest,
  AssessmentDetail,
  AttemptGradeResult,
  Classroom,
  ClassroomCreateRequest,
  ClassroomMembersReplaceRequest,
  GradeAppendRequest,
  Gradebook,
  GradingStatus,
  ItemStatistics,
  ScoreImportPreview,
  ScoreImportResult,
  Session,
  SessionDetail,
  Student,
  StudentCreateRequest,
  StudentPage,
} from '@/types/assessment'
import {
  assessmentItemPath,
  assessmentsPath,
  assessmentSessionItemPath,
  assessmentSessionsPath,
  attemptGradesPath,
  classroomStudentsPath,
  classroomsPath,
  gradebookExcelPath,
  gradebookPath,
  gradeImportPath,
  gradingFinalizePath,
  gradingStartPath,
  itemStatisticsPath,
  studentsPath,
} from '@/lib/assessments'

/**
 * 409 冲突的可识别错误:
 * - kind='revision':乐观锁失败(评测状态/成绩被他人改动)。
 * - kind='status':评分状态前置不满足(如非评分中不能录分 / 已定稿只读)。
 * - kind='batch':batch_id 被其它请求复用。
 * - kind='duplicate':唯一约束冲突(学号 / 班级名 / 用户绑定)。
 * - kind='other':其它 409。
 */
export class AssessmentConflictError extends Error {
  readonly status = 409
  readonly kind: 'revision' | 'status' | 'batch' | 'duplicate' | 'other'
  readonly detail: string

  constructor(detail: string) {
    super(detail || 'conflict')
    this.name = 'AssessmentConflictError'
    this.detail = detail
    if (/版本冲突|已变更|revision/i.test(detail)) this.kind = 'revision'
    else if (/batch_id/i.test(detail)) this.kind = 'batch'
    else if (/只有|已定稿|状态|不能再修改/i.test(detail)) this.kind = 'status'
    else if (/已存在|绑定/i.test(detail)) this.kind = 'duplicate'
    else this.kind = 'other'
  }
}

function extractStatus(err: unknown): number | undefined {
  const e = err as { status?: number; statusCode?: number; response?: { status?: number } }
  return e?.status ?? e?.statusCode ?? e?.response?.status
}

function extractDetail(err: unknown): string {
  const e = err as {
    data?: { detail?: string }
    response?: { _data?: { detail?: string } }
  }
  return e?.data?.detail ?? e?.response?._data?.detail ?? ''
}

function mapConflict(err: unknown): never {
  if (extractStatus(err) === 409) {
    throw new AssessmentConflictError(extractDetail(err))
  }
  throw err
}

/**
 * 通用评测数据层:封装学生/班级名册、评测身份创建/列表/详情、投放 session
 * 列表/详情、评分状态流转、分页 gradebook、item 统计、追加式录分与成绩册 Excel。
 * 所有资源在学科强上下文下。409 统一映射为 {@link AssessmentConflictError};
 * 其余错误原样抛出。
 */
export function useAssessments() {
  const { $api } = useNuxtApp()

  // ------------------------------------------------------------- Students //
  const listStudents = (
    subjectId: number,
    opts: { keyword?: string; page?: number; pageSize?: number } = {},
  ) => {
    const query: Record<string, string | number> = {}
    if (opts.keyword) query.keyword = opts.keyword
    if (opts.page != null) query.page = opts.page
    if (opts.pageSize != null) query.page_size = opts.pageSize
    return $api<StudentPage>(studentsPath(subjectId), { query })
  }

  const createStudent = (subjectId: number, payload: StudentCreateRequest) =>
    $api<Student>(studentsPath(subjectId), {
      method: 'POST',
      body: payload,
    }).catch(mapConflict)

  // ----------------------------------------------------------- Classrooms //
  const listClassrooms = (subjectId: number) =>
    $api<Classroom[]>(classroomsPath(subjectId))

  const createClassroom = (subjectId: number, payload: ClassroomCreateRequest) =>
    $api<Classroom>(classroomsPath(subjectId), {
      method: 'POST',
      body: payload,
    }).catch(mapConflict)

  const listClassroomStudents = (subjectId: number, classroomId: number) =>
    $api<Student[]>(classroomStudentsPath(subjectId, classroomId))

  const replaceClassroomMembers = (
    subjectId: number,
    classroomId: number,
    payload: ClassroomMembersReplaceRequest,
  ) =>
    $api<Student[]>(classroomStudentsPath(subjectId, classroomId), {
      method: 'PUT',
      body: payload,
    }).catch(mapConflict)

  // -------------------------------------------------------- Assessments //
  const listAssessments = (subjectId: number, opts: { status?: string } = {}) => {
    const query: Record<string, string> = {}
    if (opts.status) query.status = opts.status
    return $api<Assessment[]>(assessmentsPath(subjectId), { query })
  }

  const createAssessment = (subjectId: number, payload: AssessmentCreateRequest) =>
    $api<SessionDetail>(assessmentsPath(subjectId), {
      method: 'POST',
      body: payload,
    }).catch(mapConflict)

  const getAssessment = (subjectId: number, assessmentId: number) =>
    $api<AssessmentDetail>(assessmentItemPath(subjectId, assessmentId))

  // --------------------------------------------------- Assessment sessions //
  const listSessions = (
    subjectId: number,
    opts: { gradingStatus?: GradingStatus; assessmentId?: number } = {},
  ) => {
    const query: Record<string, string | number> = {}
    if (opts.gradingStatus) query.grading_status = opts.gradingStatus
    if (opts.assessmentId != null) query.assessment_id = opts.assessmentId
    return $api<Session[]>(assessmentSessionsPath(subjectId), { query })
  }

  const getSession = (subjectId: number, sessionId: number) =>
    $api<SessionDetail>(assessmentSessionItemPath(subjectId, sessionId))

  const startGrading = (subjectId: number, sessionId: number) =>
    $api<SessionDetail>(gradingStartPath(subjectId, sessionId), {
      method: 'POST',
    }).catch(mapConflict)

  const finalizeGrading = (subjectId: number, sessionId: number) =>
    $api<SessionDetail>(gradingFinalizePath(subjectId, sessionId), {
      method: 'POST',
    }).catch(mapConflict)

  // ------------------------------------------------------------ Gradebook //
  const getGradebook = (
    subjectId: number,
    sessionId: number,
    opts: { page?: number; pageSize?: number } = {},
  ) => {
    const query: Record<string, number> = {}
    if (opts.page != null) query.page = opts.page
    if (opts.pageSize != null) query.page_size = opts.pageSize
    return $api<Gradebook>(gradebookPath(subjectId, sessionId), { query })
  }

  const getItemStatistics = (subjectId: number, sessionId: number) =>
    $api<ItemStatistics>(itemStatisticsPath(subjectId, sessionId))

  const exportGradebook = (subjectId: number, sessionId: number) =>
    $api<Blob>(gradebookExcelPath(subjectId, sessionId), {
      responseType: 'blob',
    })

  const previewGradeImport = (subjectId: number, sessionId: number, file: File) => {
    const body = new FormData()
    body.append('file', file)
    return $api<ScoreImportPreview>(gradeImportPath(subjectId, sessionId, 'preview'), {
      method: 'POST',
      body,
    })
  }

  const applyGradeImport = (
    subjectId: number,
    sessionId: number,
    file: File,
    batchId?: string,
  ) => {
    const body = new FormData()
    body.append('file', file)
    if (batchId != null) body.append('batch_id', batchId)
    return $api<ScoreImportResult>(gradeImportPath(subjectId, sessionId, 'apply'), {
      method: 'POST',
      body,
    }).catch(mapConflict)
  }

  // ------------------------------------------------------- Attempt grades //
  const appendGrades = (
    subjectId: number,
    attemptId: number,
    payload: GradeAppendRequest,
  ) =>
    $api<AttemptGradeResult>(attemptGradesPath(subjectId, attemptId), {
      method: 'PATCH',
      body: payload,
    }).catch(mapConflict)

  return {
    listStudents,
    createStudent,
    listClassrooms,
    createClassroom,
    listClassroomStudents,
    replaceClassroomMembers,
    listAssessments,
    createAssessment,
    getAssessment,
    listSessions,
    getSession,
    startGrading,
    finalizeGrading,
    getGradebook,
    getItemStatistics,
    exportGradebook,
    previewGradeImport,
    applyGradeImport,
    appendGrades,
  }
}
