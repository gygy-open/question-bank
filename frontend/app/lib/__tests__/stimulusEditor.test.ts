import { describe, expect, it } from 'vitest'
import type { QuestionSummary } from '@/types'
import { getApiErrorDetail, isRevisionConflict } from '@/lib/apiErrors'
import {
  addMember,
  hasEditorSubjectMismatch,
  moveMember,
  publicQuestionsUnderPrivateStimulus,
  removeMember,
  sameOrder,
} from '@/lib/stimulusEditor'

const question = (id: number, visibility: 'public' | 'private' = 'public'): QuestionSummary =>
  ({ id, visibility } as QuestionSummary)
const ids = (members: QuestionSummary[]) => members.map(member => member.id)

describe('stimulus sub-question operations', () => {
  it('adds unique questions in order', () => {
    const members = addMember([], question(2))
    expect(addMember(members, question(2))).toBe(members)
    expect(ids(addMember(members, question(5)))).toEqual([2, 5])
  })

  it('removes and reorders sub-questions', () => {
    const members = [2, 5, 8].map(id => question(id))
    expect(ids(removeMember(members, 5))).toEqual([2, 8])
    expect(ids(moveMember(members, 2, 0))).toEqual([8, 2, 5])
    expect(moveMember(members, 0, 9)).toBe(members)
  })

  it('compares order by id', () => {
    expect(sameOrder([question(1), question(2)], [question(1), question(2)])).toBe(true)
    expect(sameOrder([question(2), question(1)], [question(1), question(2)])).toBe(false)
  })
})

describe('stimulus visibility compatibility', () => {
  it('flags public questions under a private stimulus only', () => {
    const members = [question(2), question(5, 'private')]
    expect(publicQuestionsUnderPrivateStimulus('private', members)).toEqual([2])
    expect(publicQuestionsUnderPrivateStimulus('public', members)).toEqual([])
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
    expect(getApiErrorDetail({ data: { detail: '公开题目不能挂在私有材料下' } }, '保存失败'))
      .toBe('公开题目不能挂在私有材料下')
    expect(getApiErrorDetail({ data: { detail: [{ msg: 'question_ids 不可重复' }] } }, '保存失败'))
      .toBe('question_ids 不可重复')
  })
})
