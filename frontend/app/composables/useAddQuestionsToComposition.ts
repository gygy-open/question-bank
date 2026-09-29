import { useCompositions, CompositionConflictError } from '@/composables/useCompositions'
import {
  appendQuestionsToDocument,
  documentFromNodes,
  documentToReplaceRequest,
} from '@/lib/compositionDocument'
import type { CompositionScope } from '@/types/composition'
import type { Question, QuestionPage } from '@/types'

/**
 * “把题目写入某份稿件”这条链路被试题篮 / 单题快捷 / 批量直加 / 材料页整组加入共用。
 * 依赖材料的小题自动合成材料题节点，稿件已有同材料节点时并入。
 */
export function useAddQuestionsToComposition() {
  const { $api } = useNuxtApp()
  const api = useCompositions()

  const addQuestionsToComposition = async (
    subjectId: number,
    scope: CompositionScope,
    compositionId: number,
    questionIds: number[],
  ) => {
    const detail = await api.getComposition(subjectId, scope, compositionId)
    const doc = documentFromNodes(detail.nodes)
    // 并入已有材料题节点时需要其小题的实时位置，和新题一次取回。
    const existingGroupQuestionIds = doc.nodes
      .filter(node => node.nodeType === 'question_group')
      .flatMap(node => node.children)
      .map(child => child.questionId)
      .filter((id): id is number => id != null)
    const fetchIds = [...new Set([...questionIds, ...existingGroupQuestionIds])]

    // 冻结进节点前必须取最新题目内容，试题篮/列表里缓存的展示数据可能已过期。
    const page = await $api<QuestionPage>('/questions', {
      query: { ids: fetchIds, size: fetchIds.length },
    })
    const byId = new Map(page.items.map((q) => [q.id, q]))
    const freshQuestions = questionIds
      .map((id) => byId.get(id))
      .filter((q): q is Question => q != null)

    if (freshQuestions.length === 0) {
      throw new Error('题目已不存在，无法加入稿件')
    }

    const livePositions = new Map(
      page.items
        .filter(q => q.stimulus_position != null)
        .map(q => [q.id, q.stimulus_position!] as [number, number]),
    )
    const { doc: nextDoc, added } = appendQuestionsToDocument(doc, freshQuestions, livePositions)
    const batchId = globalThis.crypto?.randomUUID?.()
    const payload = documentToReplaceRequest(nextDoc, detail.revision, batchId)

    let revision: number
    try {
      const resp = await api.replaceNodes(subjectId, scope, compositionId, payload)
      revision = resp.revision
    } catch (err) {
      if (err instanceof CompositionConflictError) throw err
      throw new Error('加入稿件失败')
    }

    return {
      addedCount: added,
      compositionTitle: detail.title,
      revision,
    }
  }

  return { addQuestionsToComposition }
}
