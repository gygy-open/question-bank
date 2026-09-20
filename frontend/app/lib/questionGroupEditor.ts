import type { QuestionGroupItem, QuestionSummary } from '@/types'

export interface OrderedQuestionMember {
  question_id: number
  position: number
  question: QuestionSummary
}

export interface PublicGroupCompatibility {
  privateMaterial: boolean
  privateQuestionIds: number[]
}

export function getPublicGroupCompatibility(
  visibility: 'public' | 'private',
  material: { visibility: 'public' | 'private' } | null,
  members: OrderedQuestionMember[],
): PublicGroupCompatibility {
  if (visibility === 'private') return { privateMaterial: false, privateQuestionIds: [] }
  return {
    privateMaterial: material?.visibility === 'private',
    privateQuestionIds: members
      .filter(member => member.question.visibility === 'private')
      .map(member => member.question_id),
  }
}

export function hasEditorSubjectMismatch(
  editorSubjectId: number | null,
  currentSubjectId: number | null,
): boolean {
  return editorSubjectId !== null && editorSubjectId !== currentSubjectId
}

export function normalizeMembers(members: OrderedQuestionMember[]): OrderedQuestionMember[] {
  return members.map((member, position) => ({ ...member, position }))
}

export function addMember(
  members: OrderedQuestionMember[],
  question: QuestionSummary,
): OrderedQuestionMember[] {
  if (members.some(member => member.question_id === question.id)) return members
  return normalizeMembers([...members, { question_id: question.id, position: members.length, question }])
}

export function removeMember(
  members: OrderedQuestionMember[],
  questionId: number,
): OrderedQuestionMember[] {
  return normalizeMembers(members.filter(member => member.question_id !== questionId))
}

export function moveMember(
  members: OrderedQuestionMember[],
  fromIndex: number,
  toIndex: number,
): OrderedQuestionMember[] {
  if (fromIndex < 0 || fromIndex >= members.length || toIndex < 0 || toIndex >= members.length) {
    return members
  }
  const reordered = [...members]
  const [member] = reordered.splice(fromIndex, 1)
  if (!member) return members
  reordered.splice(toIndex, 0, member)
  return normalizeMembers(reordered)
}

export function sortAndNormalizeMembers(items: QuestionGroupItem[]): OrderedQuestionMember[] {
  return normalizeMembers([...items].sort((left, right) => left.position - right.position))
}

export function getApiErrorStatus(error: unknown): number | undefined {
  const candidate = error as { statusCode?: number, status?: number, response?: { status?: number } }
  return candidate?.statusCode ?? candidate?.status ?? candidate?.response?.status
}

export function isRevisionConflict(error: unknown): boolean {
  return getApiErrorStatus(error) === 409
}

export function getApiErrorDetail(error: unknown, fallback: string): string {
  const candidate = error as {
    data?: { detail?: unknown }
    response?: { _data?: { detail?: unknown } }
    message?: string
  }
  const detail = candidate?.data?.detail ?? candidate?.response?._data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map(item => typeof item?.msg === 'string' ? item.msg : String(item))
      .join('；')
  }
  return candidate?.message || fallback
}