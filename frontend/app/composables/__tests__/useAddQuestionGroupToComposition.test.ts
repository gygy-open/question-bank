import { beforeEach, describe, expect, it, vi } from 'vitest'

const getComposition = vi.fn()
const replaceNodes = vi.fn()

vi.mock('@/composables/useCompositions', () => ({
  CompositionConflictError: class CompositionConflictError extends Error {},
  useCompositions: () => ({ getComposition, replaceNodes }),
}))

import { useAddQuestionGroupToComposition } from '@/composables/useAddQuestionGroupToComposition'

beforeEach(() => {
  getComposition.mockReset()
  replaceNodes.mockReset()
  getComposition.mockResolvedValue({
    id: 9,
    title: '目标稿件',
    revision: 4,
    nodes: [],
  })
  replaceNodes.mockResolvedValue({ revision: 5, nodes: [] })
})

describe('useAddQuestionGroupToComposition', () => {
  it('replace 仅新增 question_group root 与 group id，children 由服务端生成', async () => {
    const { addQuestionGroupToComposition } = useAddQuestionGroupToComposition()
    const result = await addQuestionGroupToComposition(3, 'shared', 9, 27)

    expect(replaceNodes).toHaveBeenCalledOnce()
    const [subjectId, scope, compositionId, payload] = replaceNodes.mock.calls[0]!
    expect([subjectId, scope, compositionId]).toEqual([3, 'shared', 9])
    expect(payload.expected_revision).toBe(4)
    expect(payload.nodes).toHaveLength(1)
    expect(payload.nodes[0]).toMatchObject({
      node_kind: 'module',
      node_type: 'question_group',
      question_group_id: 27,
    })
    expect(payload.nodes[0].parent_id).toBeUndefined()
    expect(result).toMatchObject({ compositionTitle: '目标稿件', revision: 5, nodes: [] })
  })
})