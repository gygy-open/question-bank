import type { Publication, PublicationDetail, BlockWrite, PublicationType } from '~/types'

export interface PublicationCreatePayload {
  title: string
  pub_type?: PublicationType
  subject_id?: number | null
  description?: string | null
  difficulty?: number | null
  knowledge_point_ids?: number[] | null
}

export interface PublicationUpdatePayload {
  title?: string
  subject_id?: number | null
  description?: string | null
  status?: 'draft' | 'archived'
  difficulty?: number | null
  knowledge_point_ids?: number[] | null
}

export interface PublicationExportOptions {
  title?: string
  format: 'docx' | 'latex'
  content_position: 'after_question' | 'end_of_paper' | 'hidden'
  include_answer: boolean
  include_analysis: boolean
  include_explanation: boolean
  include_summary: boolean
  include_source: boolean
}

export interface PublicationListParams {
  pub_type?: PublicationType
  subject_id?: number | null
  status?: string
  keyword?: string
  knowledge_point_ids?: number[]
  difficulty?: number | null
  sort?: string
}

export function usePublications() {
  const { $api } = useNuxtApp()

  const list = (params?: PublicationListParams) =>
    $api<Publication[]>('/publications', { query: params })

  const get = (id: number) => $api<PublicationDetail>(`/publications/${id}`)

  const create = (payload: PublicationCreatePayload) =>
    $api<Publication>('/publications', { method: 'POST', body: payload })

  const update = (id: number, payload: PublicationUpdatePayload) =>
    $api<Publication>(`/publications/${id}`, { method: 'PATCH', body: payload })

  const remove = (id: number) =>
    $api(`/publications/${id}`, { method: 'DELETE' })

  const duplicate = (id: number) =>
    $api<Publication>(`/publications/${id}/duplicate`, { method: 'POST' })

  /** 整表覆写块 (拖拽/编辑后保存)。 */
  const saveBlocks = (id: number, blocks: BlockWrite[]) =>
    $api<PublicationDetail>(`/publications/${id}/blocks`, {
      method: 'PUT',
      body: { blocks },
    })

  /** 将若干题目作为题块追加到队尾 (试题篮加入题目)。 */
  const appendQuestions = (id: number, questionIds: number[]) =>
    $api<PublicationDetail>(`/publications/${id}/blocks/questions`, {
      method: 'POST',
      body: { question_ids: questionIds },
    })

  /** 柔性解包: 将题组内容深拷贝追加到目标出版物队尾。 */
  const importGroup = (id: number, groupId: number) =>
    $api<PublicationDetail>(`/publications/${id}/blocks/import-group/${groupId}`, {
      method: 'POST',
    })

  const download = (id: number, options: PublicationExportOptions) =>
    $api<Blob>(`/publications/${id}/download`, {
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
    download,
  }
}
