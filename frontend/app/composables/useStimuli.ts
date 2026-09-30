import type {
  Stimulus,
  StimulusBundleRequest,
  StimulusBundleUpdateRequest,
  StimulusCreateRequest,
  StimulusDetail,
  StimulusPage,
  StimulusQuestionsUpdateRequest,
  StimulusUpdateRequest,
} from '@/types'

export function useStimuli() {
  const { $api } = useNuxtApp()
  const basePath = (subjectId: number) => `/subjects/${subjectId}/stimuli`

  const listStimuli = (subjectId: number, query: Record<string, unknown> = {}) =>
    $api<StimulusPage>(basePath(subjectId), { query })

  const getStimulus = (subjectId: number, stimulusId: number) =>
    $api<StimulusDetail>(`${basePath(subjectId)}/${stimulusId}`)

  const createStimulus = (subjectId: number, payload: StimulusCreateRequest) =>
    $api<Stimulus>(basePath(subjectId), { method: 'POST', body: payload })

  const updateStimulus = (subjectId: number, stimulusId: number, payload: StimulusUpdateRequest) =>
    $api<Stimulus>(`${basePath(subjectId)}/${stimulusId}`, { method: 'PUT', body: payload })

  const setStimulusQuestions = (
    subjectId: number,
    stimulusId: number,
    payload: StimulusQuestionsUpdateRequest,
  ) =>
    $api<StimulusDetail>(`${basePath(subjectId)}/${stimulusId}/questions`, {
      method: 'PUT', body: payload,
    })

  const createStimulusBundle = (subjectId: number, payload: StimulusBundleRequest) =>
    $api<StimulusDetail>(`${basePath(subjectId)}/bundle`, { method: 'POST', body: payload })

  const updateStimulusBundle = (
    subjectId: number,
    stimulusId: number,
    payload: StimulusBundleUpdateRequest,
  ) =>
    $api<StimulusDetail>(`${basePath(subjectId)}/${stimulusId}/bundle`, {
      method: 'PUT', body: payload,
    })

  const deleteStimulus = (subjectId: number, stimulusId: number, expectedRevision: number) =>
    $api<void>(`${basePath(subjectId)}/${stimulusId}`, {
      method: 'DELETE', query: { expected_revision: expectedRevision },
    })

  const restoreStimulus = (subjectId: number, stimulusId: number, expectedRevision: number) =>
    $api<Stimulus>(`${basePath(subjectId)}/${stimulusId}/restore`, {
      method: 'POST', body: { expected_revision: expectedRevision },
    })

  return {
    listStimuli,
    getStimulus,
    createStimulus,
    updateStimulus,
    setStimulusQuestions,
    createStimulusBundle,
    updateStimulusBundle,
    deleteStimulus,
    restoreStimulus,
  }
}