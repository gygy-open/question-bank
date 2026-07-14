import { createSharedComposable, useStorage } from '@vueuse/core'

export interface BasketItem {
  id: number
  content: string
  q_type: string
}

const _usePaperBasket = () => {
  const items = useStorage<BasketItem[]>('paper-basket', [])

  const add = (item: BasketItem) => {
    if (!items.value.find(i => i.id === item.id)) {
      items.value.push(item)
    }
  }

  const remove = (id: number) => {
    items.value = items.value.filter(i => i.id !== id)
  }

  const toggle = (item: BasketItem) => {
    if (has(item.id)) {
      remove(item.id)
    } else {
      add(item)
    }
  }

  const has = (id: number) => {
    return !!items.value.find(i => i.id === id)
  }

  const clear = () => {
    items.value = []
  }

  return {
    items,
    add,
    remove,
    toggle,
    has,
    clear
  }
}

export const usePaperBasket = createSharedComposable(_usePaperBasket)
