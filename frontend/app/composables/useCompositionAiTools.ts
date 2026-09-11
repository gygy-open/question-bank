// 组稿编辑器暴露给 AI 的两个前端工具。
//
// 为什么在前端：读要读用户手里那份(可能有未保存改动的)在编文档，改也必须落在同一份上；
// 读写不同源会让模型看到的节点 id 和实际编辑目标对不上。
//
// 为什么用 onActivated/onDeactivated 而不是 mount/unmount：app.vue 是全局
// <NuxtPage keepalive />，用户导航走之后本页仍然「mounted」。用 onUnmounted 注销的话，
// 助手在别的页面依然能改这块看不见的画布。
//
// 改动不落库：applyOperations 的结果交给页面当作待确认预览，用户点「应用」才真正保存。
// 工具本身立刻返回 —— 人工确认可能要几分钟，远超后端 30s 票据与 180s run 预算。

import { onActivated, onDeactivated, onUnmounted } from 'vue'
import type { AnswerFieldKey } from '@/types/composition'
import type { Question } from '@/types'
import type { EditorDocument } from '@/lib/compositionDocument'
import { renderOutline } from '@/lib/compositionOutline'
import { diffDocuments } from '@/lib/compositionDiff'
import type { DocumentChange } from '@/lib/compositionDiff'
import { applyOperations } from '@/lib/compositionPrimitives'
import type { AiOperation } from '@/lib/compositionPrimitives'
import { registerClientTool, unregisterClientTool } from '@/composables/useAiClientTools'

export const AI_TOOL_READ_OUTLINE = 'read_composition_outline'
export const AI_TOOL_EDIT = 'edit_composition'

export interface CompositionAiToolsOptions {
  /** 当前在编文档（含未保存改动）。 */
  getDocument: () => EditorDocument
  getTitle: () => string
  getQuestionDisplay: () => Record<AnswerFieldKey, boolean>
  getNumberingEnabled: () => boolean
  getScoringEnabled: () => boolean
  /** 取实时题目用于冻结快照；绝不能用缓存的展示数据。 */
  loadQuestions: (ids: number[]) => Promise<Question[]>
  /** 有编辑权限才注册 edit 工具；viewer 只读大纲。 */
  canEdit: () => boolean
  /** 把改动挂成待确认预览（画布切到 after，等用户「应用 / 放弃」）。 */
  stagePending: (doc: EditorDocument, changes: DocumentChange[], summary: string) => void
  /** 已有未确认改动时不再受理新的一批，避免叠加出无法解释的 diff。 */
  hasPending: () => boolean
}

export function useCompositionAiTools(options: CompositionAiToolsOptions): void {
  const readOutline = async () => {
    const doc = options.getDocument()
    return {
      ok: true,
      content: renderOutline(doc, {
        title: options.getTitle(),
        questionDisplay: options.getQuestionDisplay(),
        numberingEnabled: options.getNumberingEnabled(),
        scoringEnabled: options.getScoringEnabled(),
      }),
      data: { node_count: doc.nodes.length },
    }
  }

  const edit = async (args: Record<string, any>) => {
    if (!options.canEdit()) {
      return { ok: false, content: '当前用户没有这个学科的组稿编辑权限，无法修改稿件。' }
    }
    if (options.hasPending()) {
      return {
        ok: false,
        content: '上一批改动还等着用户确认，请先让用户点「应用」或「放弃」，再提交新的改动。',
      }
    }

    const ops = (args?.operations ?? []) as AiOperation[]
    if (!Array.isArray(ops) || !ops.length) {
      return { ok: false, content: 'operations 是空的，没有可执行的操作。' }
    }

    const before = options.getDocument()
    const { doc, results } = await applyOperations(before, ops, {
      loadQuestions: options.loadQuestions,
    })
    const failed = results.filter((r) => !r.ok)
    const changes = diffDocuments(before, doc)

    if (!changes.length) {
      const reason = failed.length
        ? failed.map((r) => `${r.op}：${r.message}`).join('；')
        : '这批操作没有产生任何实际变化。'
      return { ok: false, content: reason }
    }

    const summary = typeof args?.summary === 'string' && args.summary.trim()
      ? args.summary.trim()
      : '来自助手的改动'
    options.stagePending(doc, changes, summary)

    const lines = [
      `已生成 ${changes.length} 处改动的预览，等待用户点「应用」确认后才会保存：`,
      ...changes.map((c) => `- ${c.label}`),
    ]
    if (failed.length) {
      lines.push('', '以下操作失败，其余已生效：')
      lines.push(...failed.map((r) => `- ${r.op}：${r.message}`))
    }
    return {
      ok: true,
      content: lines.join('\n'),
      data: { changes: changes.length, failed: failed.length },
    }
  }

  const register = () => {
    registerClientTool(AI_TOOL_READ_OUTLINE, readOutline)
    registerClientTool(AI_TOOL_EDIT, edit)
  }
  const unregister = () => {
    unregisterClientTool(AI_TOOL_READ_OUTLINE)
    unregisterClientTool(AI_TOOL_EDIT)
  }

  onActivated(register)
  onDeactivated(unregister)
  onUnmounted(unregister)
}
