import { describe, expect, it } from 'vitest'
import {
  type DuplicateCandidate,
  DUPLICATE_CODE,
  duplicateCandidatesFromError,
  similarityPercent,
  strongestLevel,
} from '../questionDedup'

const cand = (level: 'duplicate' | 'similar', similarity = 1): DuplicateCandidate => ({
  question_id: 1,
  level,
  similarity,
  variant: false,
  preview: '',
  q_type: 'free_response',
  status: 'draft',
  created_by: null,
  created_at: null,
  diff: [],
})

describe('questionDedup', () => {
  it('extracts candidates from a 409 duplicate error', () => {
    const candidates = [cand('duplicate')]
    expect(duplicateCandidatesFromError({ data: { code: DUPLICATE_CODE, params: { candidates } } })).toEqual(candidates)
    expect(duplicateCandidatesFromError({ response: { _data: { code: DUPLICATE_CODE, params: {} } } })).toEqual([])
  })

  it('ignores other errors', () => {
    expect(duplicateCandidatesFromError({ data: { code: 'question.not_found' } })).toBeNull()
    expect(duplicateCandidatesFromError(new Error('x'))).toBeNull()
    expect(duplicateCandidatesFromError(null)).toBeNull()
  })

  it('reports the strongest level', () => {
    expect(strongestLevel([])).toBeNull()
    expect(strongestLevel([cand('similar', 0.93)])).toBe('similar')
    expect(strongestLevel([cand('similar', 0.93), cand('duplicate')])).toBe('duplicate')
  })

  it('rounds similarity to a percentage', () => {
    expect(similarityPercent(0.926)).toBe(93)
  })
})
