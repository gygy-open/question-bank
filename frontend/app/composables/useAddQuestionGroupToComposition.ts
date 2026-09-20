import { useCompositions, CompositionConflictError } from '@/composables/useCompositions'
import {
  createQuestionGroupNode,
  documentFromNodes,
  documentToReplaceRequest,
  insertRootNodesAfter,
} from '@/lib/compositionDocument'
import type { CompositionScope } from '@/types/composition'

/** 将题组作为原生 module 加入稿件；成员与材料快照由服务端生成并在响应中返回。 */
export function useAddQuestionGroupToComposition() {
  const api = useCompositions()

  const addQuestionGroupToComposition = async (
    subjectId: number,
    scope: CompositionScope,
    compositionId: number,
    questionGroupId: number,
  ) => {
    const detail = await api.getComposition(subjectId, scope, compositionId)
    const doc = documentFromNodes(detail.nodes)
    const nextDoc = insertRootNodesAfter(
      doc,
      doc.nodes.length - 1,
      [createQuestionGroupNode(questionGroupId)],
    )
    const payload = documentToReplaceRequest(
      nextDoc,
      detail.revision,
      globalThis.crypto?.randomUUID?.(),
    )

    try {
      const response = await api.replaceNodes(subjectId, scope, compositionId, payload)
      return {
        compositionTitle: detail.title,
        revision: response.revision,
        nodes: response.nodes,
      }
    } catch (error) {
      if (error instanceof CompositionConflictError) throw error
      throw new Error('加入稿件失败')
    }
  }

  return { addQuestionGroupToComposition }
}