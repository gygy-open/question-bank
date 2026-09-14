// 成绩录入 (Assessment) 纯函数:URL 路径构建。不依赖 Nuxt 运行时,便于聚焦单测。
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

/** /subjects/{id}/exam-sessions 集合路径(创建 / 列表)。 */
export function examSessionsPath(subjectId: number): string {
  return `/subjects/${subjectId}/exam-sessions`
}

/** 单场考试路径(详情)。 */
export function examSessionItemPath(subjectId: number, examSessionId: number): string {
  return `${examSessionsPath(subjectId)}/${examSessionId}`
}

/** draft → recording 状态流转路径。 */
export function examStartRecordingPath(subjectId: number, examSessionId: number): string {
  return `${examSessionItemPath(subjectId, examSessionId)}/start-recording`
}

/** recording → locked 状态流转路径。 */
export function examLockPath(subjectId: number, examSessionId: number): string {
  return `${examSessionItemPath(subjectId, examSessionId)}/lock`
}

/** gradebook 矩阵读取路径。 */
export function examGradebookPath(subjectId: number, examSessionId: number): string {
  return `${examSessionItemPath(subjectId, examSessionId)}/gradebook`
}

/** 带隐藏并发元数据的 Excel 成绩表。 */
export function examGradebookExcelPath(subjectId: number, examSessionId: number): string {
  return `${examSessionItemPath(subjectId, examSessionId)}/gradebook.xlsx`
}

/** Excel 成绩导入预检或应用路径。 */
export function examScoreImportPath(
  subjectId: number,
  examSessionId: number,
  action: 'preview' | 'apply',
): string {
  return `${examSessionItemPath(subjectId, examSessionId)}/score-imports/${action}`
}

/** 单个参与者逐题成绩保存路径。 */
export function examResultPath(
  subjectId: number,
  examSessionId: number,
  resultId: number,
): string {
  return `${examSessionItemPath(subjectId, examSessionId)}/results/${resultId}`
}
