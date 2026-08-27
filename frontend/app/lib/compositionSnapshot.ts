// 组稿版本 snapshot v2 只读纯函数：仅消费不可变快照，绝不查询当前题库。
// 与后端 _build_snapshot 语义对齐：节点前序展平（root 按 position，module 子节点紧随其后）；
// answer_item 通过同一 snapshot 内 source question 节点解析答案，并按「有效字段」渲染
// （effective = included && (override ?? module.fields[field]))。

import type {
  AnswerFieldKey,
  CompositionSnapshotV2,
  QuestionSnapshot,
  SnapshotAnswerItemNode,
  SnapshotNode,
  SnapshotQuestionDetailsNode,
  SnapshotQuestionNode,
} from '@/types/composition'
import { ANSWER_FIELD_KEYS } from '@/types/composition'

/** 带 module 子节点的树节点（仅 question_details 携带非空 children）。 */
export type SnapshotTreeNode = SnapshotNode & { children: SnapshotNode[] }

/** 把前序展平的 snapshot 节点折叠为「root + module 子树」，供渲染时避免重复遍历子节点。 */
export function buildSnapshotTree(snapshot: CompositionSnapshotV2): SnapshotTreeNode[] {
  const childrenByParent = new Map<string, SnapshotNode[]>()
  const roots: SnapshotNode[] = []
  for (const node of snapshot.nodes) {
    if (node.parent_id == null) {
      roots.push(node)
    } else {
      const arr = childrenByParent.get(node.parent_id) ?? []
      arr.push(node)
      childrenByParent.set(node.parent_id, arr)
    }
  }
  const byPos = (list: SnapshotNode[]) =>
    [...list].sort((a, b) => a.position - b.position || a.id.localeCompare(b.id))

  return byPos(roots).map((node) => ({
    ...node,
    children: node.node_type === 'question_details' ? byPos(childrenByParent.get(node.id) ?? []) : [],
  }))
}

/** 建立 question 节点 UUID → SnapshotQuestionNode 映射（answer_item.source_question_node_id 解析用）。 */
export function snapshotQuestionNodeMap(
  snapshot: CompositionSnapshotV2,
): Map<string, SnapshotQuestionNode> {
  const map = new Map<string, SnapshotQuestionNode>()
  for (const node of snapshot.nodes) {
    if (node.node_type === 'question') map.set(node.id, node)
  }
  return map
}

/** 计算 answer_item 相对 module 全局开关的「有效字段」：included && (override ?? module 全局)。 */
export function effectiveAnswerFields(
  moduleNode: SnapshotQuestionDetailsNode,
  answerItem: SnapshotAnswerItemNode,
): Record<AnswerFieldKey, boolean> {
  const global = moduleNode.props.fields
  const overrides = answerItem.props.overrides
  const included = answerItem.props.included
  const out = {} as Record<AnswerFieldKey, boolean>
  for (const key of ANSWER_FIELD_KEYS) {
    const override = overrides[key]
    const base = override == null ? Boolean(global[key]) : override
    out[key] = included && base
  }
  return out
}

/** 已解析的 answer_item：source 题目快照 + 有效字段 + 是否有任一字段可见。 */
export interface ResolvedAnswerItem {
  answerItem: SnapshotAnswerItemNode
  question: QuestionSnapshot | null
  fields: Record<AnswerFieldKey, boolean>
  anyVisible: boolean
}

/** 解析单个 module 的 answer_item 子节点为可渲染投影（缺失 source/题目时 question 为 null）。 */
export function resolveModuleAnswerItems(
  moduleNode: SnapshotTreeNode,
  questionNodeMap: Map<string, SnapshotQuestionNode>,
): ResolvedAnswerItem[] {
  if (moduleNode.node_type !== 'question_details') return []
  const out: ResolvedAnswerItem[] = []
  for (const child of moduleNode.children) {
    if (child.node_type !== 'answer_item') continue
    const source = questionNodeMap.get(child.source_question_node_id)
    const fields = effectiveAnswerFields(moduleNode, child)
    out.push({
      answerItem: child,
      question: source?.question ?? null,
      fields,
      anyVisible: ANSWER_FIELD_KEYS.some((k) => fields[k]),
    })
  }
  return out
}

/** 题号：仅当定稿时刻冻结的 numbering_enabled 为真才输出;旧快照缺失该字段视为关闭。 */
export function resolvedQuestionNumber(node: SnapshotQuestionNode, snapshot: CompositionSnapshotV2): string {
  if (!snapshot.numbering_enabled) return ''
  return node.props?.number ?? ''
}

/** 分值：仅当定稿时刻冻结的 scoring_enabled 为真才输出;旧快照缺失该字段视为关闭。 */
export function resolvedQuestionScore(node: SnapshotQuestionNode, snapshot: CompositionSnapshotV2): number | null {
  if (!snapshot.scoring_enabled) return null
  const s = node.props?.score
  return typeof s === 'number' ? s : null
}

/** 题目级 show 覆盖 ?? 定稿时刻冻结的全局默认;旧快照缺失 question_display 视为全局默认全部隐藏。 */
export function effectiveQuestionDisplay(
  node: SnapshotQuestionNode,
  snapshot: CompositionSnapshotV2,
  key: AnswerFieldKey,
): boolean {
  const override = node.props?.show?.[key]
  if (typeof override === 'boolean') return override
  return Boolean(snapshot.question_display?.[key])
}
