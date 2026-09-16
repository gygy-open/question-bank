import { describe, it, expect } from 'vitest'
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

describe('assessments path helpers', () => {
  it('学生 / 班级集合路径', () => {
    expect(studentsPath(3)).toBe('/subjects/3/students')
    expect(classroomsPath(3)).toBe('/subjects/3/classrooms')
  })

  it('班级成员路径', () => {
    expect(classroomStudentsPath(3, 7)).toBe('/subjects/3/classrooms/7/students')
  })

  it('评测身份集合 / 详情路径', () => {
    expect(assessmentsPath(3)).toBe('/subjects/3/assessments')
    expect(assessmentItemPath(3, 5)).toBe('/subjects/3/assessments/5')
  })

  it('投放 session 集合 / 详情路径', () => {
    expect(assessmentSessionsPath(3)).toBe('/subjects/3/assessment-sessions')
    expect(assessmentSessionItemPath(3, 9)).toBe('/subjects/3/assessment-sessions/9')
  })

  it('评分流转 / gradebook / 统计 / 导入路径', () => {
    expect(gradingStartPath(3, 9)).toBe('/subjects/3/assessment-sessions/9/grading/start')
    expect(gradingFinalizePath(3, 9)).toBe('/subjects/3/assessment-sessions/9/grading/finalize')
    expect(gradebookPath(3, 9)).toBe('/subjects/3/assessment-sessions/9/gradebook')
    expect(itemStatisticsPath(3, 9)).toBe('/subjects/3/assessment-sessions/9/item-statistics')
    expect(gradebookExcelPath(3, 9)).toBe('/subjects/3/assessment-sessions/9/gradebook.xlsx')
    expect(gradeImportPath(3, 9, 'preview')).toBe('/subjects/3/assessment-sessions/9/grade-imports/preview')
    expect(gradeImportPath(3, 9, 'apply')).toBe('/subjects/3/assessment-sessions/9/grade-imports/apply')
  })

  it('attempt 追加式录分路径', () => {
    expect(attemptGradesPath(3, 42)).toBe('/subjects/3/assessment-attempts/42/grades')
  })
})
