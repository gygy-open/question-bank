// AI 改动的变更清单 —— 按节点 id 配对算出 before/after 的差异。
//
// 不用文本行 diff（也就不需要引第三方库）：本领域的最小单位是节点，节点有稳定 UUID，
// 按 id 配对能直接说出「新增 / 删除 / 移动 / 修改」，而行 diff 会把节点身份丢掉。
//
// 真正的「预览」是画布直接切到 after 文档；这份清单只负责解释画布上发生了什么。

import type { AnswerFieldKey } from '@/types/composition'
import { ANSWER_FIELD_KEYS } from '@/types/composition'
import { richDocToPlainText } from '@/components/rich-editor/richDoc'
import type { EditorDocument, EditorNode } from '@/lib/compositionDocument'
import { FIELD_LABELS, describeNode } from '@/lib/compositionOutline'
import {
  answerSpacePropsOf,
  detailPropsOf,
  headingLevelOf,
  questionNumberOf,
  questionScoreOf,
  questionShowOverride,
} from '@/lib/compositionDocument'

export type ChangeKind = 'added' | 'removed' | 'moved' | 'modified'

export interface DocumentChange {
  kind: ChangeKind
  nodeId: string
  /** 一句话描述，直接展示给用户。 */
  label: string
}

/** 同一个节点改了什么；返回空数组表示没有可见改动。 */
function propChanges(before: EditorNode, after: EditorNode): string[] {
  const out: string[] = []
  if (before.nodeType !== after.nodeType) return ['类型变更']

  switch (after.nodeType) {
    case 'question': {
      const b = questionNumberOf(before)
      const a = questionNumberOf(after)
      if (b !== a) out.push(`题号 ${b || '无'} → ${a || '无'}`)
      const bs = questionScoreOf(before)
      const as = questionScoreOf(after)
      if (bs !== as) out.push(`分值 ${bs ?? '无'} → ${as ?? '无'}`)
      for (const key of ANSWER_FIELD_KEYS) {
        const bv = questionShowOverride(before, key)
        const av = questionShowOverride(after, key)
        if (bv === av) continue
        const text = av == null ? '跟随全局' : av ? '显示' : '隐藏'
        out.push(`${FIELD_LABELS[key]}${text}`)
      }
      break
    }
    case 'heading': {
      if (headingLevelOf(before) !== headingLevelOf(after)) {
        out.push(`层级 ${headingLevelOf(before)} → ${headingLevelOf(after)}`)
      }
      if (richDocToPlainText(before.content) !== richDocToPlainText(after.content)) out.push('文字变更')
      break
    }
    case 'rich_text':
      if (richDocToPlainText(before.content) !== richDocToPlainText(after.content)) out.push('文字变更')
      break
    case 'answer_space': {
      const b = answerSpacePropsOf(before)
      const a = answerSpacePropsOf(after)
      if (b.lines !== a.lines) out.push(`行数 ${b.lines} → ${a.lines}`)
      if (b.style !== a.style) out.push('样式变更')
      break
    }
    case 'question_details': {
      const b = detailPropsOf(before)
      const a = detailPropsOf(after)
      if (b.scope !== a.scope) out.push(`收录范围 ${b.scope} → ${a.scope}`)
      const fields = ANSWER_FIELD_KEYS.filter((k) => Boolean(b.fields[k]) !== Boolean(a.fields[k]))
      if (fields.length) out.push(`展示字段调整（${fields.map((k) => FIELD_LABELS[k]).join('、')}）`)
      break
    }
    default:
      break
  }
  return out
}

/**
 * 最小移动集：保留下来的节点里，不属于「最长保序子序列」的那些才算被移动。
 * 直接比下标会把一次交换算成两个节点都动了，清单会吵。
 */
function movedNodeIds(before: EditorDocument, after: EditorDocument): Set<string> {
  const beforeOrder = new Map(before.nodes.map((n, i) => [n.id, i]))
  const survivors = after.nodes.filter((n) => beforeOrder.has(n.id))
  const seq = survivors.map((n) => beforeOrder.get(n.id)!)

  // 耐心排序求 LIS，用 parent 指针回溯出具体是哪几个。
  const tails: number[] = []
  const parent = new Array<number>(seq.length).fill(-1)
  for (let i = 0; i < seq.length; i += 1) {
    let lo = 0
    let hi = tails.length
    while (lo < hi) {
      const mid = (lo + hi) >> 1
      if (seq[tails[mid]!]! < seq[i]!) lo = mid + 1
      else hi = mid
    }
    if (lo > 0) parent[i] = tails[lo - 1]!
    tails[lo] = i
  }

  const kept = new Set<string>()
  for (let i = tails.length ? tails[tails.length - 1]! : -1; i >= 0; i = parent[i]!) {
    kept.add(survivors[i]!.id)
  }
  return new Set(survivors.filter((n) => !kept.has(n.id)).map((n) => n.id))
}

/**
 * 计算 before → after 的变更清单，按 after 的版面顺序排列（删除项挂在它原来的位置上）。
 * answer_item 是规范化派生的，不参与 diff —— 它的变化必然是某个题目或模块变化的结果。
 */
export function diffDocuments(before: EditorDocument, after: EditorDocument): DocumentChange[] {
  const beforeById = new Map(before.nodes.map((n) => [n.id, n]))
  const afterIds = new Set(after.nodes.map((n) => n.id))
  const movedIds = movedNodeIds(before, after)

  const changes: DocumentChange[] = []

  for (const node of after.nodes) {
    const prev = beforeById.get(node.id)
    if (!prev) {
      changes.push({ kind: 'added', nodeId: node.id, label: `新增 ${describeNode(node)}` })
      continue
    }
    const props = propChanges(prev, node)
    if (props.length) {
      changes.push({
        kind: 'modified',
        nodeId: node.id,
        label: `修改 ${describeNode(node)}：${props.join('，')}`,
      })
    }
    if (movedIds.has(node.id)) {
      changes.push({ kind: 'moved', nodeId: node.id, label: `移动 ${describeNode(node)}` })
    }
  }

  for (const node of before.nodes) {
    if (afterIds.has(node.id)) continue
    changes.push({ kind: 'removed', nodeId: node.id, label: `删除 ${describeNode(node)}` })
  }

  return changes
}
