import type { QuestionSummary } from '@/types'

export function hasEditorSubjectMismatch(
  editorSubjectId: number | null,
  currentSubjectId: number | null,
): boolean {
  return editorSubjectId !== null && editorSubjectId !== currentSubjectId
}

export function addMember(members: QuestionSummary[], question: QuestionSummary): QuestionSummary[] {
  if (members.some(member => member.id === question.id)) return members
  return [...members, question]
}

export function removeMember(members: QuestionSummary[], questionId: number): QuestionSummary[] {
  return members.filter(member => member.id !== questionId)
}

export function moveMember(
  members: QuestionSummary[],
  fromIndex: number,
  toIndex: number,
): QuestionSummary[] {
  if (fromIndex < 0 || fromIndex >= members.length || toIndex < 0 || toIndex >= members.length) {
    return members
  }
  const reordered = [...members]
  const [member] = reordered.splice(fromIndex, 1)
  if (!member) return members
  reordered.splice(toIndex, 0, member)
  return reordered
}

/** 私有材料下不能挂公开小题;返回违反该规则的小题 ID。 */
export function publicQuestionsUnderPrivateStimulus(
  stimulusVisibility: 'public' | 'private',
  members: QuestionSummary[],
): number[] {
  if (stimulusVisibility !== 'private') return []
  return members.filter(member => member.visibility === 'public').map(member => member.id)
}

export function sameOrder(left: QuestionSummary[], right: QuestionSummary[]): boolean {
  return left.length === right.length && left.every((member, index) => member.id === right[index]?.id)
}
