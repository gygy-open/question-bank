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

  return { listMaterials, getMaterial, createMaterial, updateMaterial }
}