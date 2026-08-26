import { describe, it, expect } from 'vitest'
import {
  buildSnapshotTree,
  effectiveAnswerFields,
  resolveModuleAnswerItems,
  snapshotQuestionNodeMap,
} from '@/lib/compositionSnapshot'
import type {
  CompositionSnapshotV2,
  QuestionSnapshot,
  SnapshotAnswerItemNode,
  SnapshotNode,
  SnapshotQuestionDetailsNode,
} from '@/types/composition'

function richDoc(text: string) {
  return { type: 'doc' as const, content: [{ type: 'paragraph', content: [{ type: 'text', text }] }] }
}

function qsnap(id: number): QuestionSnapshot {
  return {
    id,
    content_revision: 1,
    content_schema_version: 2,
    q_type: 'single_choice',
    content: richDoc(`Q${id}`),
    options: [{ id: 'opt_a', label: 'A', content: richDoc('A') }],
    answer: { kind: 'single_choice', correct: 'opt_a' },
    thinking: null,
    analysis: richDoc(`解析${id}`),
    summary: null,
    difficulty: 3,
    source: 'seed',
  }
}

function questionNode(nodeId: string, position: number, q: QuestionSnapshot): SnapshotNode {
  return {
    id: nodeId,
    parent_id: null,
    slot: null,
    position,
    schema_version: 1,
    node_kind: 'block',
    node_type: 'question',
    question_id: q.id,
    question_revision: q.content_revision,
    question: q,
  }
}

function moduleNode(
  nodeId: string,
  position: number,
  fields: SnapshotQuestionDetailsNode['props']['fields'],
): SnapshotNode {
  return {
    id: nodeId,
    parent_id: null,
    slot: null,
    position,
    schema_version: 1,
    node_kind: 'module',
    node_type: 'question_details',
    props: { scope: 'all', fields },
  }
}

function answerItem(
  nodeId: string,
  parentId: string,
  position: number,
  sourceId: string,
  props: SnapshotAnswerItemNode['props'],
): SnapshotNode {
  return {
    id: nodeId,
    parent_id: parentId,
    slot: 'body',
    position,
    schema_version: 1,
    node_kind: 'reference',
    node_type: 'answer_item',
    source_question_node_id: sourceId,
    props,
  }
}

function snapshot(nodes: SnapshotNode[]): CompositionSnapshotV2 {
  return {
    schema_version: 2,
    composition_id: 1,
    source_revision: 2,
    title: '稿件',
    subject_id: 1,
    finalized_at: '2026-01-01T00:00:00Z',
    nodes,
  }
}

describe('buildSnapshotTree', () => {
  it('按 position 排序并把 module 子节点挂到 children，root 层不含子节点', () => {
    const snap = snapshot([
      answerItem('ai1', 'm1', 0, 'q1', { included: true, overrides: { answer: null, thinking: null, analysis: null, summary: null } }),
      moduleNode('m1', 1, { answer: true, thinking: false, analysis: false, summary: false }),
      questionNode('q1', 0, qsnap(1)),
    ])
    const tree = buildSnapshotTree(snap)
    expect(tree.map((n) => n.id)).toEqual(['q1', 'm1'])
    expect(tree.every((n) => n.parent_id == null)).toBe(true)
    const mod = tree.find((n) => n.id === 'm1')!
    expect(mod.children.map((c) => c.id)).toEqual(['ai1'])
  })
})

describe('effectiveAnswerFields', () => {
  const mod = moduleNode('m1', 0, { answer: true, thinking: false, analysis: true, summary: false }) as SnapshotQuestionDetailsNode

  it('override=null 继承 module 全局开关', () => {
    const ai = answerItem('ai', 'm1', 0, 'q1', { included: true, overrides: { answer: null, thinking: null, analysis: null, summary: null } }) as SnapshotAnswerItemNode
    expect(effectiveAnswerFields(mod, ai)).toEqual({ answer: true, thinking: false, analysis: true, summary: false })
  })

  it('override 显式覆盖全局', () => {
    const ai = answerItem('ai', 'm1', 0, 'q1', { included: true, overrides: { answer: false, thinking: true, analysis: null, summary: null } }) as SnapshotAnswerItemNode
    expect(effectiveAnswerFields(mod, ai)).toEqual({ answer: false, thinking: true, analysis: true, summary: false })
  })

  it('included=false 时全部字段不可见', () => {
    const ai = answerItem('ai', 'm1', 0, 'q1', { included: false, overrides: { answer: true, thinking: true, analysis: true, summary: true } }) as SnapshotAnswerItemNode
    expect(effectiveAnswerFields(mod, ai)).toEqual({ answer: false, thinking: false, analysis: false, summary: false })
  })
})

describe('resolveModuleAnswerItems', () => {
  it('按 source 节点解析题目并计算有效字段与可见性', () => {
    const snap = snapshot([
      questionNode('q1', 0, qsnap(1)),
      questionNode('q2', 1, qsnap(2)),
      moduleNode('m1', 2, { answer: true, thinking: false, analysis: false, summary: false }),
      answerItem('ai1', 'm1', 0, 'q1', { included: true, overrides: { answer: null, thinking: null, analysis: null, summary: null } }),
      answerItem('ai2', 'm1', 1, 'q2', { included: false, overrides: { answer: null, thinking: null, analysis: null, summary: null } }),
    ])
    const tree = buildSnapshotTree(snap)
    const map = snapshotQuestionNodeMap(snap)
    const mod = tree.find((n) => n.id === 'm1')!
    const resolved = resolveModuleAnswerItems(mod, map)
    expect(resolved.map((r) => r.question?.id)).toEqual([1, 2])
    expect(resolved[0]!.anyVisible).toBe(true)
    expect(resolved[1]!.anyVisible).toBe(false)
  })

  it('source 题目缺失时 question 为 null', () => {
    const snap = snapshot([
      moduleNode('m1', 0, { answer: true, thinking: false, analysis: false, summary: false }),
      answerItem('ai1', 'm1', 0, 'missing', { included: true, overrides: { answer: null, thinking: null, analysis: null, summary: null } }),
    ])
    const tree = buildSnapshotTree(snap)
    const mod = tree.find((n) => n.id === 'm1')!
    const resolved = resolveModuleAnswerItems(mod, snapshotQuestionNodeMap(snap))
    expect(resolved[0]!.question).toBeNull()
  })
})
