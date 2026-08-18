import type { Composition, CompositionDetail, BlockWrite, CompositionScope, CompositionSettings, TemplateItem } from '~/types'

export interface CompositionCreatePayload {
  title: string
  folder_id?: number | null
  subject_id?: number | null
  scope?: CompositionScope | null
  description?: string | null
  difficulty?: number | null
  meta_data?: CompositionSettings | null
}

export interface CompositionUpdatePayload {
  title?: string
  description?: string | null
  status?: 'draft' | 'published' | 'archived'
  difficulty?: number | null
  folder_id?: number | null
  meta_data?: CompositionSettings | null
}

export interface CompositionExportOptions {
  title?: string
  format: 'docx' | 'latex'
}

export interface CompositionListParams {
  scope?: CompositionScope
  subject_id?: number | null
  folder_id?: number | null
  status?: string
  keyword?: string
  difficulty?: number | null
  sort?: string
}

export interface CreateFromTemplatePayload {
  source?: 'system' | 'custom'
  key?: string | null
  template_id?: number | null
  title?: string | null
  folder_id?: number | null
  subject_id?: number | null
  scope?: CompositionScope | null
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

  /** 新建起点列表: 系统预置模板 + 当前学科可见的自定义模板。 */
  const listTemplates = (subjectId?: number | null) =>
    $api<TemplateItem[]>('/compositions/templates/list', {
      query: { subject_id: subjectId ?? undefined },
    })

  /** 从模板新建 = 一次深拷贝, 不留来源关联。 */
  const createFromTemplate = (payload: CreateFromTemplatePayload) =>
    $api<Composition>('/compositions/templates/new', { method: 'POST', body: payload })

  /** 把现有文档另存为自定义模板。 */
  const saveAsTemplate = (id: number, payload: { title?: string, scope?: CompositionScope }) =>
    $api<Composition>(`/compositions/${id}/save-as-template`, { method: 'POST', body: payload })

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
    listTemplates,
    createFromTemplate,
    saveAsTemplate,
    download,
  }
}
