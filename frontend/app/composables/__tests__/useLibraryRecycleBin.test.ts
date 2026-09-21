import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useMaterials } from '@/composables/useMaterials'
import { useQuestionGroups } from '@/composables/useQuestionGroups'

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

describe('题目材料与题组回收站请求', () => {
  it('删除把 expected_revision 放到 query', async () => {
    await useMaterials().deleteMaterial(3, 7, 2)
    await useQuestionGroups().deleteQuestionGroup(3, 9, 4)

    expect(calls[0]).toEqual({
      url: '/subjects/3/stimuli/7',
      opts: { method: 'DELETE', query: { expected_revision: 2 } },
    })
    expect(calls[1]).toEqual({
      url: '/subjects/3/question-groups/9',
      opts: { method: 'DELETE', query: { expected_revision: 4 } },
    })
  })

  it('恢复命中 restore 路径并发送 expected_revision body', async () => {
    await useMaterials().restoreMaterial(3, 7, 3)
    await useQuestionGroups().restoreQuestionGroup(3, 9, 5)

    expect(calls[0]).toEqual({
      url: '/subjects/3/stimuli/7/restore',
      opts: { method: 'POST', body: { expected_revision: 3 } },
    })
    expect(calls[1]).toEqual({
      url: '/subjects/3/question-groups/9/restore',
      opts: { method: 'POST', body: { expected_revision: 5 } },
    })
  })
})
