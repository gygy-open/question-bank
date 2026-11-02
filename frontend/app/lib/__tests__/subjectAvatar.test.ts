import { describe, expect, it } from 'vitest'
import { getSubjectIcon, getSubjectInitial } from '../subjectAvatar'

describe('subjectAvatar', () => {
  it('maps common subject names to an icon', () => {
    for (const name of ['High School Mathematics', '初中物理', 'Chemistry', '生物', '英语', '语文', '历史', '地理', '信息技术']) {
      expect(getSubjectIcon(name), name).not.toBeNull()
    }
  })

  it('returns null for unknown subjects', () => {
    expect(getSubjectIcon('Zzz Qqq')).toBeNull()
  })

  it('uses two initials for multi-word Latin names', () => {
    expect(getSubjectInitial('Zzz Qqq Www')).toBe('ZQ')
    expect(getSubjectInitial('Philosophy')).toBe('P')
  })

  it('uses the first character for CJK names', () => {
    expect(getSubjectInitial('哲学')).toBe('哲')
    expect(getSubjectInitial('  ')).toBe('?')
  })
})
