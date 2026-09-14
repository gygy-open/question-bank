import type {
  Classroom,
  ClassroomCreateRequest,
  ClassroomMembersReplaceRequest,
  ExamSession,
  ExamSessionCreateRequest,
  ExamSessionDetail,
  ExamSessionStatus,
  Gradebook,
  Result,
  ScoreSaveRequest,
  ScoreImportPreview,
  ScoreImportResult,
  Student,
  StudentCreateRequest,
  StudentPage,
} from '@/types/assessment'
import {
  classroomStudentsPath,
  classroomsPath,
  examGradebookPath,
  examGradebookExcelPath,
  examLockPath,
  examResultPath,
  examSessionItemPath,
  examSessionsPath,
  examScoreImportPath,
  examStartRecordingPath,
  studentsPath,
} from '@/lib/assessments'

/**
 * 409 冲突的可识别错误:
 * - kind='revision':乐观锁失败(成绩/考试被他人改动)。
 * - kind='status':状态前置不满足(如非 recording 不能录分)。
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
    else if (/只有.*状态|只有.*考试可以|状态/i.test(detail)) this.kind = 'status'
    else if (/已存在|已.*绑定/i.test(detail)) this.kind = 'duplicate'
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
 * 成绩录入数据层:封装学生/班级名册、考试创建/列表/详情、状态流转、
 * gradebook 读取与逐题录分。所有资源在学科强上下文下。
 * 409 统一映射为 {@link AssessmentConflictError};其余错误原样抛出。
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

  // -------------------------------------------------------- Exam sessions //
  const listExamSessions = (
    subjectId: number,
    opts: { status?: ExamSessionStatus; classroomId?: number } = {},
  ) => {
    const query: Record<string, string | number> = {}
    if (opts.status) query.status = opts.status
    if (opts.classroomId != null) query.classroom_id = opts.classroomId
    return $api<ExamSession[]>(examSessionsPath(subjectId), { query })
  }

  const createExamSession = (subjectId: number, payload: ExamSessionCreateRequest) =>
    $api<ExamSessionDetail>(examSessionsPath(subjectId), {
      method: 'POST',
      body: payload,
    }).catch(mapConflict)

  const getExamSession = (subjectId: number, examSessionId: number) =>
    $api<ExamSessionDetail>(examSessionItemPath(subjectId, examSessionId))

  const startRecording = (subjectId: number, examSessionId: number) =>
    $api<ExamSessionDetail>(examStartRecordingPath(subjectId, examSessionId), {
      method: 'POST',
    }).catch(mapConflict)

  const lockExamSession = (subjectId: number, examSessionId: number) =>
    $api<ExamSessionDetail>(examLockPath(subjectId, examSessionId), {
      method: 'POST',
    }).catch(mapConflict)

  // ------------------------------------------------------------ Gradebook //
  const getGradebook = (subjectId: number, examSessionId: number) =>
    $api<Gradebook>(examGradebookPath(subjectId, examSessionId))

  const exportGradebook = (subjectId: number, examSessionId: number) =>
    $api<Blob>(examGradebookExcelPath(subjectId, examSessionId), {
      responseType: 'blob',
    })

  const previewScoreImport = (subjectId: number, examSessionId: number, file: File) => {
    const body = new FormData()
    body.append('file', file)
    return $api<ScoreImportPreview>(examScoreImportPath(subjectId, examSessionId, 'preview'), {
      method: 'POST',
      body,
    })
  }

  const applyScoreImport = (
    subjectId: number,
    examSessionId: number,
    file: File,
    batchId: string,
  ) => {
    const body = new FormData()
    body.append('file', file)
    body.append('batch_id', batchId)
    return $api<ScoreImportResult>(examScoreImportPath(subjectId, examSessionId, 'apply'), {
      method: 'POST',
      body,
    }).catch(mapConflict)
  }

  const saveScores = (
    subjectId: number,
    examSessionId: number,
    resultId: number,
    payload: ScoreSaveRequest,
  ) =>
    $api<Result>(examResultPath(subjectId, examSessionId, resultId), {
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
    listExamSessions,
    createExamSession,
    getExamSession,
    startRecording,
    lockExamSession,
    getGradebook,
    exportGradebook,
    previewScoreImport,
    applyScoreImport,
    saveScores,
  }
}
