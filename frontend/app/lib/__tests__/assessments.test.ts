import { describe, it, expect } from 'vitest'
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

describe('assessments path helpers', () => {
  it('学生 / 班级集合路径', () => {
    expect(studentsPath(3)).toBe('/subjects/3/students')
    expect(classroomsPath(3)).toBe('/subjects/3/classrooms')
  })

  it('班级成员路径', () => {
    expect(classroomStudentsPath(3, 7)).toBe('/subjects/3/classrooms/7/students')
  })

  it('考试集合 / 详情路径', () => {
    expect(examSessionsPath(3)).toBe('/subjects/3/exam-sessions')
    expect(examSessionItemPath(3, 9)).toBe('/subjects/3/exam-sessions/9')
  })

  it('状态流转 / gradebook / 录分路径', () => {
    expect(examStartRecordingPath(3, 9)).toBe('/subjects/3/exam-sessions/9/start-recording')
    expect(examLockPath(3, 9)).toBe('/subjects/3/exam-sessions/9/lock')
    expect(examGradebookPath(3, 9)).toBe('/subjects/3/exam-sessions/9/gradebook')
    expect(examGradebookExcelPath(3, 9)).toBe('/subjects/3/exam-sessions/9/gradebook.xlsx')
    expect(examScoreImportPath(3, 9, 'preview')).toBe('/subjects/3/exam-sessions/9/score-imports/preview')
    expect(examScoreImportPath(3, 9, 'apply')).toBe('/subjects/3/exam-sessions/9/score-imports/apply')
    expect(examResultPath(3, 9, 42)).toBe('/subjects/3/exam-sessions/9/results/42')
  })
})
