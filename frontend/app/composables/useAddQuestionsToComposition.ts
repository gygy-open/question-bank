import { useCompositions, CompositionConflictError } from '@/composables/useCompositions'
import {
  createQuestionNode,
  documentFromNodes,
  documentToReplaceRequest,
  insertRootNodesAfter,
} from '@/lib/compositionDocument'
import type { CompositionScope } from '@/types/composition'
import type { Question, QuestionPage } from '@/types'

/** “把题目写入某份稿件”这条链路被试题篮 / 单题快捷 / 批量直加共用，逻辑集中在此，避免三处各写一份。 */
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

    // 冻结进节点前必须取最新题目内容，试题篮/列表里缓存的展示数据可能已过期。
    const page = await $api<QuestionPage>('/questions', {
      query: { ids: questionIds, size: questionIds.length },
    })
    const byId = new Map(page.items.map((q) => [q.id, q]))
    const freshQuestions = questionIds
      .map((id) => byId.get(id))
      .filter((q): q is Question => q != null)

    if (freshQuestions.length === 0) {
      throw new Error('题目已不存在，无法加入稿件')
    }

    const doc = documentFromNodes(detail.nodes)
    const nextDoc = insertRootNodesAfter(
      doc,
      doc.nodes.length - 1,
      freshQuestions.map(createQuestionNode),
    )
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
      addedCount: freshQuestions.length,
      compositionTitle: detail.title,
      revision,
    }
  }

  return { addQuestionsToComposition }
}
