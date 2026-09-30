import type { QuestionStatus, QuestionSummary, QuestionType, RichDoc, AnswerSpec, OptionSpec } from '@/types'
import {
  type QuestionDraft,
  buildQuestionPayload,
  createEmptyDraft,
  dbQuestionToDraft,
  hasOptionPool,
  validateQuestionDraft,
} from '@/lib/questionModel'

type Visibility = 'public' | 'private'

export function hasEditorSubjectMismatch(
  editorSubjectId: number | null,
  currentSubjectId: number | null,
): boolean {
  return editorSubjectId !== null && editorSubjectId !== currentSubjectId
}

/** 材料题编辑器中的一道小题：新建小题只有本地草稿，已有小题带 id 与加载时的题目内容快照。 */
export interface MemberEntry {
  key: string
  id?: number
  draft: QuestionDraft
  baseline: string | null
}

export interface QuestionBody {
  content: RichDoc
  q_type: QuestionType
  options: OptionSpec[] | null
  answer: AnswerSpec | null
  thinking: RichDoc
  analysis: RichDoc
  summary: RichDoc
  difficulty: number
}

/** 小题就地编辑只改题目内容；知识点/标签等不在此处编辑，保存时不能被覆盖。 */
export function questionBody(draft: QuestionDraft): QuestionBody {
  return {
    content: draft.content,
    q_type: draft.q_type,
    options: hasOptionPool(draft.q_type) ? draft.options : null,
    answer: draft.answer,
    thinking: draft.thinking,
    analysis: draft.analysis,
    summary: draft.summary,
    difficulty: draft.difficulty,
  }
}

let entrySeq = 0
const nextKey = (prefix: string) => `${prefix}-${++entrySeq}`

export function entryFromQuestion(question: QuestionSummary): MemberEntry {
  const draft = dbQuestionToDraft(question as Parameters<typeof dbQuestionToDraft>[0])
  return { key: `q-${question.id}`, id: question.id, draft, baseline: JSON.stringify(questionBody(draft)) }
}

export function newEntry(meta: { status: QuestionStatus, visibility: Visibility }): MemberEntry {
  const draft = createEmptyDraft()
  draft.status = meta.status
  draft.visibility = meta.visibility
  return { key: nextKey('new'), draft, baseline: null }
}

export function isBodyDirty(entry: MemberEntry): boolean {
  return entry.baseline === null || JSON.stringify(questionBody(entry.draft)) !== entry.baseline
}

export function addExisting(entries: MemberEntry[], questions: QuestionSummary[]): MemberEntry[] {
  const known = new Set(entries.map(entry => entry.id).filter(id => id != null))
  return [...entries, ...questions.filter(question => !known.has(question.id)).map(entryFromQuestion)]
}

export function moveMember<T>(members: T[], fromIndex: number, toIndex: number): T[] {
  if (fromIndex < 0 || fromIndex >= members.length || toIndex < 0 || toIndex >= members.length) {
    return members
  }
  const reordered = [...members]
  const [member] = reordered.splice(fromIndex, 1)
  if (member === undefined) return members
  reordered.splice(toIndex, 0, member)
  return reordered
}

export interface BundleMeta {
  status: QuestionStatus
  visibility: Visibility
  /** 材料题的状态/可见性被修改时，所有小题随之一致。 */
  syncMembers: boolean
}

export function effectiveMeta(entry: MemberEntry, meta: BundleMeta): { status: QuestionStatus, visibility: Visibility } {
  if (entry.id == null || meta.syncMembers) return { status: meta.status, visibility: meta.visibility }
  return { status: entry.draft.status, visibility: entry.draft.visibility }
}

/** 私有材料题下不能有公开小题；返回违规小题的序号（从 1 开始）。 */
export function publicMembersUnderPrivate(entries: MemberEntry[], meta: BundleMeta): number[] {
  if (meta.visibility !== 'private') return []
  return entries
    .map((entry, index) => (effectiveMeta(entry, meta).visibility === 'public' ? index + 1 : 0))
    .filter(Boolean)
}

export function validateMembers(entries: MemberEntry[], meta: BundleMeta): string | null {
  for (const [index, entry] of entries.entries()) {
    if (!isBodyDirty(entry) && !meta.syncMembers) continue
    const error = validateQuestionDraft({ ...entry.draft, ...effectiveMeta(entry, meta) })
    if (error) return `第 ${index + 1} 小题：${error}`
  }
  return null
}

export type BundleQuestion =
  | { create: Record<string, unknown> }
  | { id: number, update?: Record<string, unknown> }

export function buildBundleQuestions(entries: MemberEntry[], meta: BundleMeta): BundleQuestion[] {
  return entries.map((entry) => {
    const target = effectiveMeta(entry, meta)
    if (entry.id == null) {
      const { subject_id: _subjectId, ...payload } = buildQuestionPayload(entry.draft)
      return { create: { ...payload, ...target } }
    }
    const update: Record<string, unknown> = isBodyDirty(entry) ? { ...questionBody(entry.draft) } : {}
    if (target.status !== entry.draft.status) update.status = target.status
    if (target.visibility !== entry.draft.visibility) update.visibility = target.visibility
    return Object.keys(update).length ? { id: entry.id, update } : { id: entry.id }
  })
}

/** 用于整体脏检查的可比较快照。 */
export function bundleSnapshot(stimulus: { content: RichDoc, status: QuestionStatus, visibility: Visibility, source: string }, entries: MemberEntry[]): string {
  return JSON.stringify({
    ...stimulus,
    source: stimulus.source.trim(),
    members: entries.map(entry => [entry.id ?? entry.key, questionBody(entry.draft)]),
  })
}
