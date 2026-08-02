import type { Paper, PaperDetail } from '~/types'

export interface PaperCreatePayload {
  title: string
  subject_id?: number | null
  description?: string | null
}

export interface PaperUpdatePayload {
  title?: string
  subject_id?: number | null
  description?: string | null
  status?: 'draft' | 'archived'
}

export interface PaperExportOptions {
  title?: string
  format: 'docx' | 'latex'
  include_answer: boolean
  include_analysis: boolean
  include_explanation: boolean
  include_summary: boolean
  include_source: boolean
}

interface LegacyBasketItem {
  id: number
  content: string
  q_type: string
}

const LEGACY_KEY = 'paper-basket'

export function usePapers() {
  const { $api } = useNuxtApp()

  const list = (params?: { status?: string; keyword?: string; sort?: string }) =>
    $api<Paper[]>('/papers', { query: params })

  const get = (id: number) => $api<PaperDetail>(`/papers/${id}`)

  const create = (payload: PaperCreatePayload) =>
    $api<Paper>('/papers', { method: 'POST', body: payload })

  const update = (id: number, payload: PaperUpdatePayload) =>
    $api<Paper>(`/papers/${id}`, { method: 'PATCH', body: payload })

  const remove = (id: number) =>
    $api(`/papers/${id}`, { method: 'DELETE' })

  const duplicate = (id: number) =>
    $api<Paper>(`/papers/${id}/duplicate`, { method: 'POST' })

  const addItems = (id: number, questionIds: number[]) =>
    $api<PaperDetail>(`/papers/${id}/items`, {
      method: 'POST',
      body: { question_ids: questionIds },
    })

  const removeItem = (id: number, itemId: number) =>
    $api<PaperDetail>(`/papers/${id}/items/${itemId}`, { method: 'DELETE' })

  const updateItem = (
    id: number,
    itemId: number,
    payload: { section_title?: string | null; score?: number | null },
  ) =>
    $api<PaperDetail>(`/papers/${id}/items/${itemId}`, {
      method: 'PATCH',
      body: payload,
    })

  const reorder = (id: number, orderedItemIds: number[]) =>
    $api<PaperDetail>(`/papers/${id}/items/order`, {
      method: 'PUT',
      body: { ordered_item_ids: orderedItemIds },
    })

  const download = (id: number, options: PaperExportOptions) =>
    $api<Blob>(`/papers/${id}/download`, {
      method: 'POST',
      body: options,
      responseType: 'blob',
    })

  /**
   * 一次性迁移浏览器本地旧试题篮到后端"快速试卷"，成功后清除 localStorage。
   */
  const migrateLegacyBasket = async (): Promise<number | null> => {
    if (typeof window === 'undefined') return null
    const raw = window.localStorage.getItem(LEGACY_KEY)
    if (!raw) return null

    let items: LegacyBasketItem[] = []
    try {
      items = JSON.parse(raw)
    } catch {
      window.localStorage.removeItem(LEGACY_KEY)
      return null
    }

    if (!Array.isArray(items) || items.length === 0) {
      window.localStorage.removeItem(LEGACY_KEY)
      return null
    }

    try {
      const paper = await create({ title: '快速试卷' })
      await addItems(paper.id, items.map((i) => i.id))
      window.localStorage.removeItem(LEGACY_KEY)
      return paper.id
    } catch {
      return null
    }
  }

  return {
    list,
    get,
    create,
    update,
    remove,
    duplicate,
    addItems,
    removeItem,
    updateItem,
    reorder,
    download,
    migrateLegacyBasket,
  }
}
