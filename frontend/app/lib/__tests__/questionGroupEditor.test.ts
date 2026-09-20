import { describe, expect, it } from 'vitest'
import type { QuestionSummary } from '@/types'
import {
  addMember,
  getApiErrorDetail,
  getPublicGroupCompatibility,
  hasEditorSubjectMismatch,
  isRevisionConflict,
  moveMember,
  normalizeMembers,
  removeMember,
} from '@/lib/questionGroupEditor'

const question = (id: number): QuestionSummary => ({ id } as QuestionSummary)

describe('question group member operations', () => {
  it('adds unique questions and normalizes positions', () => {
    const members = addMember([], question(2))
    expect(addMember(members, question(2))).toBe(members)
    expect(addMember(members, question(5)).map(item => [item.question_id, item.position]))
      .toEqual([[2, 0], [5, 1]])
  })

  it('removes and reorders members with contiguous positions', () => {
    const members = normalizeMembers([2, 5, 8].map((id, position) => ({
      question_id: id,
      position: position + 4,
      question: question(id),
    })))
    expect(removeMember(members, 5).map(item => [item.question_id, item.position]))
      .toEqual([[2, 0], [8, 1]])
    expect(moveMember(members, 2, 0).map(item => [item.question_id, item.position]))
      .toEqual([[8, 0], [2, 1], [5, 2]])
  })
})

describe('public group compatibility', () => {
  const member = (id: number, visibility: 'public' | 'private') => ({
    question_id: id,
    position: 0,
    question: { id, visibility } as QuestionSummary,
  })

  it('reports private materials and questions selected by a public group', () => {
    expect(getPublicGroupCompatibility(
      'public',
      { visibility: 'private' },
      [member(2, 'public'), member(5, 'private')],
    )).toEqual({ privateMaterial: true, privateQuestionIds: [5] })
  })

  it('allows private resources in a private group', () => {
    expect(getPublicGroupCompatibility(
      'private',
      { visibility: 'private' },
      [member(5, 'private')],
    )).toEqual({ privateMaterial: false, privateQuestionIds: [] })
  })
})

describe('editor subject ownership', () => {
  it('detects when the global subject no longer owns the draft', () => {
    expect(hasEditorSubjectMismatch(2, 5)).toBe(true)
    expect(hasEditorSubjectMismatch(2, 2)).toBe(false)
    expect(hasEditorSubjectMismatch(null, 5)).toBe(false)
  })
})

describe('editor API error detection', () => {
  it('recognizes revision conflicts across fetch error shapes', () => {
    expect(isRevisionConflict({ statusCode: 409 })).toBe(true)
    expect(isRevisionConflict({ response: { status: 409 } })).toBe(true)
    expect(isRevisionConflict({ statusCode: 422 })).toBe(false)
  })

  it('renders validation details', () => {
    expect(getApiErrorDetail({ data: { detail: '公开题组不能引用私有材料' } }, '保存失败'))
      .toBe('公开题组不能引用私有材料')
    expect(getApiErrorDetail({ data: { detail: [{ msg: '题组至少包含一道题' }] } }, '保存失败'))
      .toBe('题组至少包含一道题')
  })
})