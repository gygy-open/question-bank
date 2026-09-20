import type { QuestionGroup, QuestionGroupUpdateRequest, QuestionGroupWriteRequest } from '@/types'

export function useQuestionGroups() {
  const { $api } = useNuxtApp()
  const basePath = (subjectId: number) => `/subjects/${subjectId}/question-groups`

  const getQuestionGroup = (subjectId: number, groupId: number) =>
    $api<QuestionGroup>(`${basePath(subjectId)}/${groupId}`)

  const createQuestionGroup = (subjectId: number, payload: QuestionGroupWriteRequest) =>
    $api<QuestionGroup>(basePath(subjectId), { method: 'POST', body: payload })

  const updateQuestionGroup = (subjectId: number, groupId: number, payload: QuestionGroupUpdateRequest) =>
    $api<QuestionGroup>(`${basePath(subjectId)}/${groupId}`, { method: 'PUT', body: payload })

  return { getQuestionGroup, createQuestionGroup, updateQuestionGroup }
}