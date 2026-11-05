/**
 * 命题篮(规格 §12.3 N4):从题干结构面板、相关题结果中挑选条件 / 设问 / 元素组,跨题拼装新题。
 *
 * 与试题篮同样的模式:模块级单例 + localStorage 持久化;只存展示用的轻量字段,
 * 提交时由后端按 id 重新取内容并校验(必须来自可见题目的已采纳拆解、同一学科)。
 */

/** 命题篮条目。 */
export interface ComposeBasketItem {
  kind: 'element' | 'ask' | 'group'
  id: number
  question_id: number
  subject_id: number | null
  /** 展示用:条目内容(元素组为各条件以「；」连接)。 */
  content: string
}

const STORAGE_KEY = 'compose-basket'

const items = ref<ComposeBasketItem[]>([])
let loaded = false

function loadFromStorage(): void {
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

function persist(): void {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(items.value))
}

export function useComposeBasket() {
  loadFromStorage()

  const count = computed(() => items.value.length)

  function has(kind: ComposeBasketItem['kind'], id: number): boolean {
    return items.value.some(item => item.kind === kind && item.id === id)
  }

  /** 加入命题篮;只允许同一学科的条目放在一起(不同学科时先清空)。返回是否清空过。 */
  function add(item: ComposeBasketItem): boolean {
    if (has(item.kind, item.id)) return false
    const switched = items.value.length > 0 && items.value[0]!.subject_id !== item.subject_id
    items.value = switched ? [item] : [...items.value, item]
    persist()
    return switched
  }

  function remove(kind: ComposeBasketItem['kind'], id: number): void {
    items.value = items.value.filter(item => !(item.kind === kind && item.id === id))
    persist()
  }

  function clear(): void {
    items.value = []
    persist()
  }

  return { items: readonly(items), count, has, add, remove, clear }
}
