import type { Stimulus, StimulusCreateRequest, StimulusPage, StimulusUpdateRequest } from '@/types'

export function useMaterials() {
  const { $api } = useNuxtApp()
  const basePath = (subjectId: number) => `/subjects/${subjectId}/stimuli`

  const listMaterials = (subjectId: number, query: Record<string, unknown> = {}) =>
    $api<StimulusPage>(basePath(subjectId), { query })

  const getMaterial = (subjectId: number, materialId: number) =>
    $api<Stimulus>(`${basePath(subjectId)}/${materialId}`)

  const createMaterial = (subjectId: number, payload: StimulusCreateRequest) =>
    $api<Stimulus>(basePath(subjectId), { method: 'POST', body: payload })

  const updateMaterial = (subjectId: number, materialId: number, payload: StimulusUpdateRequest) =>
    $api<Stimulus>(`${basePath(subjectId)}/${materialId}`, { method: 'PUT', body: payload })

  const deleteMaterial = (subjectId: number, materialId: number, expectedRevision: number) =>
    $api<void>(`${basePath(subjectId)}/${materialId}`, {
      method: 'DELETE', query: { expected_revision: expectedRevision },
    })

  const restoreMaterial = (subjectId: number, materialId: number, expectedRevision: number) =>
    $api<Stimulus>(`${basePath(subjectId)}/${materialId}/restore`, {
      method: 'POST', body: { expected_revision: expectedRevision },
    })

  return { listMaterials, getMaterial, createMaterial, updateMaterial, deleteMaterial, restoreMaterial }
}