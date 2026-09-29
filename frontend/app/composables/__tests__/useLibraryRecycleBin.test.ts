import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useMaterials } from '@/composables/useMaterials'

let calls: Array<{ url: string, opts: any }>
const $api = vi.fn((url: string, opts: any) => {
  calls.push({ url, opts })
  return Promise.resolve({})
})

beforeEach(() => {
  calls = []
  vi.stubGlobal('useNuxtApp', () => ({ $api }))
})

afterEach(() => {
  vi.unstubAllGlobals()
  $api.mockClear()
})

describe('题目材料回收站与小题请求', () => {
  it('删除把 expected_revision 放到 query', async () => {
    await useMaterials().deleteMaterial(3, 7, 2)

    expect(calls[0]).toEqual({
      url: '/subjects/3/stimuli/7',
      opts: { method: 'DELETE', query: { expected_revision: 2 } },
    })
  })

  it('恢复命中 restore 路径并发送 expected_revision body', async () => {
    await useMaterials().restoreMaterial(3, 7, 3)

    expect(calls[0]).toEqual({
      url: '/subjects/3/stimuli/7/restore',
      opts: { method: 'POST', body: { expected_revision: 3 } },
    })
  })

  it('整体设置小题走材料的 questions 子资源', async () => {
    await useMaterials().setMaterialQuestions(3, 7, { expected_revision: 4, question_ids: [9, 2] })

    expect(calls[0]).toEqual({
      url: '/subjects/3/stimuli/7/questions',
      opts: { method: 'PUT', body: { expected_revision: 4, question_ids: [9, 2] } },
    })
  })
})
