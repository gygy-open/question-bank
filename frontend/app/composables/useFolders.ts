import type { Folder, CompositionScope } from '~/types'

export interface FolderCreatePayload {
  name: string
  subject_id: number
  scope?: CompositionScope | null
  parent_id?: number | null
}

export interface FolderUpdatePayload {
  name?: string
  parent_id?: number | null
}

export interface FolderListParams {
  subject_id?: number | null
  scope?: CompositionScope | null
}

export function useFolders() {
  const { $api } = useNuxtApp()

  const list = (params: FolderListParams) =>
    $api<Folder[]>('/folders', { query: params })

  const create = (payload: FolderCreatePayload) =>
    $api<Folder>('/folders', { method: 'POST', body: payload })

  const update = (id: number, payload: FolderUpdatePayload) =>
    $api<Folder>(`/folders/${id}`, { method: 'PATCH', body: payload })

  const remove = (id: number) =>
    $api(`/folders/${id}`, { method: 'DELETE' })

  return { list, create, update, remove }
}
