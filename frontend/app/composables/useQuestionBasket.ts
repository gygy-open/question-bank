import type { QuestionType } from '~/types'

/** 试题篮条目：仅存展示用轻量字段，加入稿件时必须重新拉取最新题目数据，不能直接复用这里的内容。 */
export interface QuestionBasketItem {
  id: number
  subject_id: number
  content_preview: string
  q_type: QuestionType
  difficulty: number
}

const STORAGE_KEY = 'question-basket'

// 模块级单例状态：所有页面共享同一个试题篮，localStorage 持久化跨刷新/跨页面保留。
const items = ref<QuestionBasketItem[]>([])
let loaded = false

function loadFromStorage() {
  if (loaded || typeof window === 'undefined') return
  loaded = true
  const raw = window.localStorage.getItem(STORAGE_KEY)
  if (!raw) return
  try {
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) items.value = parsed
  } catch {
    window.localStorage.removeItem(STORAGE_KEY)
  }
}

function persist() {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(items.value))
}

export function useQuestionBasket() {
  loadFromStorage()

  const count = computed(() => items.value.length)

  const has = (id: number) => items.value.some((i) => i.id === id)

  const add = (item: QuestionBasketItem) => {
    if (has(item.id)) return
    items.value = [...items.value, item]
    persist()
  }

  const addMany = (newItems: QuestionBasketItem[]) => {
    const existing = new Set(items.value.map((i) => i.id))
    const toAdd = newItems.filter((i) => !existing.has(i.id))
    if (toAdd.length === 0) return
    items.value = [...items.value, ...toAdd]
    persist()
  }

  const remove = (id: number) => {
    items.value = items.value.filter((i) => i.id !== id)
    persist()
  }

  const removeMany = (ids: number[]) => {
    const idSet = new Set(ids)
    items.value = items.value.filter((i) => !idSet.has(i.id))
    persist()
  }

  const toggle = (item: QuestionBasketItem) => {
    if (has(item.id)) remove(item.id)
    else add(item)
  }

  // subjectId 缺省时清空整个试题篮，否则只清空该学科分组。
  const clear = (subjectId?: number) => {
    items.value = subjectId == null ? [] : items.value.filter((i) => i.subject_id !== subjectId)
    persist()
  }

  const groupedBySubject = computed(() => {
    const map = new Map<number, QuestionBasketItem[]>()
    for (const item of items.value) {
      const arr = map.get(item.subject_id) ?? []
      arr.push(item)
      map.set(item.subject_id, arr)
    }
    return map
  })

  return {
    items: computed(() => items.value),
    count,
    has,
    add,
    addMany,
    remove,
    removeMany,
    toggle,
    clear,
    groupedBySubject,
  }
}
