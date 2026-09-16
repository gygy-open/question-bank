// 通用评测 (Assessment) 纯函数:URL 路径构建。不依赖 Nuxt 运行时,便于聚焦单测。
//
// 所有资源都在学科强上下文下:/subjects/{subjectId}/...

/** /subjects/{id}/students 集合路径(创建 / 分页搜索)。 */
export function studentsPath(subjectId: number): string {
  return `/subjects/${subjectId}/students`
}

/** /subjects/{id}/classrooms 集合路径(创建 / 列表)。 */
export function classroomsPath(subjectId: number): string {
  return `/subjects/${subjectId}/classrooms`
}

/** 班级成员整体替换 / 当前成员读取路径。 */
export function classroomStudentsPath(subjectId: number, classroomId: number): string {
  return `${classroomsPath(subjectId)}/${classroomId}/students`
}

// --------------------------------------------------------------------------- //
// 评测身份
// --------------------------------------------------------------------------- //
/** /subjects/{id}/assessments 集合路径(创建 / 列表)。 */
export function assessmentsPath(subjectId: number): string {
  return `/subjects/${subjectId}/assessments`
}

/** 单个评测身份路径(详情)。 */
export function assessmentItemPath(subjectId: number, assessmentId: number): string {
  return `${assessmentsPath(subjectId)}/${assessmentId}`
}

// --------------------------------------------------------------------------- //
// 投放 session
// --------------------------------------------------------------------------- //
/** /subjects/{id}/assessment-sessions 集合路径(列表)。 */
export function assessmentSessionsPath(subjectId: number): string {
  return `/subjects/${subjectId}/assessment-sessions`
}

/** 单场投放路径(详情)。 */
export function assessmentSessionItemPath(subjectId: number, sessionId: number): string {
  return `${assessmentSessionsPath(subjectId)}/${sessionId}`
}

/** not_started → in_progress 评分流转路径。 */
export function gradingStartPath(subjectId: number, sessionId: number): string {
  return `${assessmentSessionItemPath(subjectId, sessionId)}/grading/start`
}

/** in_progress → finalized 评分流转路径。 */
export function gradingFinalizePath(subjectId: number, sessionId: number): string {
  return `${assessmentSessionItemPath(subjectId, sessionId)}/grading/finalize`
}

/** gradebook 矩阵读取路径(分页)。 */
export function gradebookPath(subjectId: number, sessionId: number): string {
  return `${assessmentSessionItemPath(subjectId, sessionId)}/gradebook`
}

/** item 统计读取路径。 */
export function itemStatisticsPath(subjectId: number, sessionId: number): string {
  return `${assessmentSessionItemPath(subjectId, sessionId)}/item-statistics`
}

/** 带隐藏并发元数据的 Excel 成绩表导出。 */
export function gradebookExcelPath(subjectId: number, sessionId: number): string {
  return `${assessmentSessionItemPath(subjectId, sessionId)}/gradebook.xlsx`
}

/** Excel 成绩导入预检或应用路径。 */
export function gradeImportPath(
  subjectId: number,
  sessionId: number,
  action: 'preview' | 'apply',
): string {
  return `${assessmentSessionItemPath(subjectId, sessionId)}/grade-imports/${action}`
}

// --------------------------------------------------------------------------- //
// attempt 追加式录分
// --------------------------------------------------------------------------- //
/** 对某个 attempt 追加式录分路径。 */
export function attemptGradesPath(subjectId: number, attemptId: number): string {
  return `/subjects/${subjectId}/assessment-attempts/${attemptId}/grades`
}
