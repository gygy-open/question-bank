import { describe, expect, it } from 'vitest'
import { filterPromptManageableSubjects } from '@/lib/subjectPromptAccess'

const subjects = [
  { id: 1, name: '数学' },
  { id: 2, name: '物理' },
]

describe('filterPromptManageableSubjects', () => {
  it('returns every accessible subject for a superuser', () => {
    expect(filterPromptManageableSubjects(subjects, {
      is_superuser: true,
      capabilities: {},
    })).toEqual(subjects)
  })

  it('returns only subjects with manage_subject permission', () => {
    expect(filterPromptManageableSubjects(subjects, {
      is_superuser: false,
      capabilities: {
        '1': ['view_question', 'manage_subject'],
        '2': ['view_question', 'edit_question'],
      },
    })).toEqual([subjects[0]])
  })

  it('returns no subjects before permissions are loaded', () => {
    expect(filterPromptManageableSubjects(subjects, null)).toEqual([])
  })
})