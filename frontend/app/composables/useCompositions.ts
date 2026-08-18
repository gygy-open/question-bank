import type { Composition, CompositionDetail, BlockWrite, CompType, CompositionScope } from '~/types'

export interface CompositionCreatePayload {
  title: string
  comp_type?: CompType
  folder_id?: number | null
  subject_id?: number | null
  scope?: CompositionScope | null
  description?: string | null
  difficulty?: number | null
}

export interface CompositionUpdatePayload {
  title?: string
  description?: string | null
  status?: 'draft' | 'published' | 'archived'
  difficulty?: number | null
  folder_id?: number | null
}

export interface CompositionExportOptions {
  title?: string
  format: 'docx' | 'latex'
  content_position: 'after_question' | 'end_of_paper' | 'hidden'
  include_answer: boolean
  include_analysis: boolean
  include_explanation: boolean
  include_summary: boolean
  include_source: boolean
}

export interface CompositionListParams {
  scope?: CompositionScope
  subject_id?: number | null
  comp_type?: CompType
  folder_id?: number | null
  status?: string
  keyword?: string
  difficulty?: number | null
  sort?: string
}

export function useCompositions() {
  const { $api } = useNuxtApp()

  const list = (params?: CompositionListParams) =>
    $api<Composition[]>('/compositions', { query: params })

  const get = (id: number) => $api<CompositionDetail>(`/compositions/${id}`)

  const create = (payload: CompositionCreatePayload) =>
    $api<Composition>('/compositions', { method: 'POST', body: payload })

  const update = (id: number, payload: CompositionUpdatePayload) =>
    $api<Composition>(`/compositions/${id}`, { method: 'PATCH', body: payload })

  const remove = (id: number) =>
    $api(`/compositions/${id}`, { method: 'DELETE' })

  const duplicate = (id: number) =>
    $api<Composition>(`/compositions/${id}/duplicate`, { method: 'POST' })

  /** 整表覆写块 (拖拽/编辑后保存)。 */
  const saveBlocks = (id: number, blocks: BlockWrite[]) =>
    $api<CompositionDetail>(`/compositions/${id}/blocks`, {
      method: 'PUT',
      body: { blocks },
    })

  /** 将若干题目作为题块追加到队尾 (试题篮加入题目)。 */
  const appendQuestions = (id: number, questionIds: number[]) =>
    $api<CompositionDetail>(`/compositions/${id}/blocks/questions`, {
      method: 'POST',
      body: { question_ids: questionIds },
    })

  /** 引用式插入题组: 追加一个 component_ref 块 (跟随更新)。 */
  const importGroup = (id: number, groupId: number) =>
    $api<CompositionDetail>(`/compositions/${id}/blocks/import-group/${groupId}`, {
      method: 'POST',
    })

  /** 拆开: 将某 component_ref 块展开为深拷贝的普通块。 */
  const detachComponent = (id: number, blockId: number) =>
    $api<CompositionDetail>(`/compositions/${id}/blocks/${blockId}/detach`, {
      method: 'POST',
    })

  const download = (id: number, options: CompositionExportOptions) =>
    $api<Blob>(`/compositions/${id}/download`, {
      method: 'POST',
      body: options,
      responseType: 'blob',
    })

  return {
    list,
    get,
    create,
    update,
    remove,
    duplicate,
    saveBlocks,
    appendQuestions,
    importGroup,
    detachComponent,
    download,
  }
}
