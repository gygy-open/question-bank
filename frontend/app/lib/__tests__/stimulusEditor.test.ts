import { describe, expect, it } from 'vitest'
import type { QuestionSummary } from '@/types'
import { getApiErrorDetail, isRevisionConflict } from '@/lib/apiErrors'
import {
  type BundleMeta,
  addExisting,
  buildBundleQuestions,
  bundleSnapshot,
  entryFromQuestion,
  hasEditorSubjectMismatch,
  isBodyDirty,
  moveMember,
  newEntry,
  publicMembersUnderPrivate,
  validateMembers,
} from '@/lib/stimulusEditor'

const doc = (text: string) => ({ type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text }] }] })
const question = (id: number, overrides: Partial<QuestionSummary> = {}): QuestionSummary => ({
  id,
  content: doc(`第 ${id} 题`),
  q_type: 'free_response',
  status: 'published',
  difficulty: 3,
  visibility: 'public',
  answer: { kind: 'free_response', reference: null },
  created_at: '',
  updated_at: '',
  ...overrides,
} as QuestionSummary)
const meta = (overrides: Partial<BundleMeta> = {}): BundleMeta =>
  ({ status: 'draft', visibility: 'public', syncMembers: false, ...overrides })

describe('stimulus member entries', () => {
  it('adds existing questions once and keeps order', () => {
    const entries = addExisting([], [question(2), question(5)])
    expect(addExisting(entries, [question(2)]).map(entry => entry.id)).toEqual([2, 5])
    expect(moveMember(entries, 1, 0).map(entry => entry.id)).toEqual([5, 2])
    expect(moveMember(entries, 0, 9)).toBe(entries)
  })

  it('tracks body edits of existing questions but not unchanged ones', () => {
    const entry = entryFromQuestion(question(3))
    expect(isBodyDirty(entry)).toBe(false)
    entry.draft.content = doc('改过')
    expect(isBodyDirty(entry)).toBe(true)
    expect(isBodyDirty(newEntry({ status: 'draft', visibility: 'public' }))).toBe(true)
  })
})

describe('bundle payload', () => {
  it('creates new questions with the stimulus meta and keeps untouched members as ids', () => {
    const existing = entryFromQuestion(question(7))
    const created = newEntry({ status: 'draft', visibility: 'private' })
    created.draft.content = doc('新小题')
    const payload = buildBundleQuestions([created, existing], meta({ visibility: 'private' }))
    expect(payload[1]).toEqual({ id: 7 })
    const create = (payload[0] as { create: Record<string, unknown> }).create
    expect(create).toMatchObject({ content: doc('新小题'), status: 'draft', visibility: 'private' })
    expect(create).not.toHaveProperty('subject_id')
  })

  it('sends only question body fields for edited members, never tags or knowledge points', () => {
    const entry = entryFromQuestion(question(4))
    entry.draft.content = doc('新题干')
    const [item] = buildBundleQuestions([entry], meta())
    const update = (item as { update: Record<string, unknown> }).update
    expect(update.content).toEqual(doc('新题干'))
    expect(update).not.toHaveProperty('tag_ids')
    expect(update).not.toHaveProperty('knowledge_point_ids')
    expect(update).not.toHaveProperty('status')
  })

  it('syncs status and visibility to all members when the stimulus meta changes', () => {
    const entry = entryFromQuestion(question(4))
    const [item] = buildBundleQuestions([entry], meta({ status: 'draft', visibility: 'private', syncMembers: true }))
    expect(item).toEqual({ id: 4, update: { status: 'draft', visibility: 'private' } })
  })

  it('snapshot changes with content, order and member edits', () => {
    const stimulus = { content: doc('材料'), status: 'draft' as const, visibility: 'public' as const, source: '' }
    const entries = [entryFromQuestion(question(1)), entryFromQuestion(question(2))]
    const base = bundleSnapshot(stimulus, entries)
    expect(bundleSnapshot({ ...stimulus, source: '  ' }, entries)).toBe(base)
    expect(bundleSnapshot(stimulus, moveMember(entries, 0, 1))).not.toBe(base)
    entries[0]!.draft.difficulty = 5
    expect(bundleSnapshot(stimulus, entries)).not.toBe(base)
  })
})

describe('stimulus member validation', () => {
  it('flags public members under a private stimulus unless meta is synced', () => {
    const entries = [entryFromQuestion(question(2)), entryFromQuestion(question(5, { visibility: 'private' }))]
    expect(publicMembersUnderPrivate(entries, meta({ visibility: 'private' }))).toEqual([1])
    expect(publicMembersUnderPrivate(entries, meta({ visibility: 'private', syncMembers: true }))).toEqual([])
    expect(publicMembersUnderPrivate(entries, meta())).toEqual([])
  })

  it('reports the first invalid new or edited member by position', () => {
    const untouched = entryFromQuestion(question(1, { content: null }))
    const created = newEntry({ status: 'draft', visibility: 'public' })
    expect(validateMembers([untouched, created], meta())).toBe('第 2 小题：题干不能为空')
    created.draft.content = doc('题干')
    expect(validateMembers([untouched, created], meta())).toBeNull()
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
