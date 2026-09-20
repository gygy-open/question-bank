import { describe, expect, it } from 'vitest'
import { buildLibraryQuery } from '../libraryQueries'

describe('buildLibraryQuery', () => {
  it('omits empty and all-option values', () => {
    expect(buildLibraryQuery({ keyword: '', status: '0', stimulus_id: undefined, question_id: null })).toEqual({})
  })

  it('preserves explicit false membership filters and deep-link ids', () => {
    expect(buildLibraryQuery({ page: 2, in_question_group: false, question_id: 18 })).toEqual({
      page: 2,
      in_question_group: false,
      question_id: 18,
    })
  })
})