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

  const deleteQuestionGroup = (subjectId: number, groupId: number, expectedRevision: number) =>
    $api<void>(`${basePath(subjectId)}/${groupId}`, {
      method: 'DELETE', query: { expected_revision: expectedRevision },
    })

  const restoreQuestionGroup = (subjectId: number, groupId: number, expectedRevision: number) =>
    $api<QuestionGroup>(`${basePath(subjectId)}/${groupId}/restore`, {
      method: 'POST', body: { expected_revision: expectedRevision },
    })

  return {
    getQuestionGroup, createQuestionGroup, updateQuestionGroup,
    deleteQuestionGroup, restoreQuestionGroup,
  }
}