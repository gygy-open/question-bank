import { describe, it, expect } from 'vitest'
import {
  createAnswerSpaceNode,
  createHeadingNode,
  createQuestionDetailsModule,
  createQuestionNode,
  createRichTextNode,
  detailPropsOf,
  headingLevelOf,
  headingTextToDoc,
  normalizeDocument,
  questionNumberOf,
  questionScoreOf,
  questionShowOverride,
} from '@/lib/compositionDocument'
import type { EditorDocument, EditorNode } from '@/lib/compositionDocument'
import { applyOperations } from '@/lib/compositionPrimitives'
import type { AiOperation, ApplyDeps } from '@/lib/compositionPrimitives'
import type { Question } from '@/types'

function richDoc(text: string) {
  return { type: 'doc' as const, content: [{ type: 'paragraph', content: [{ type: 'text', text }] }] }
}

function fakeQuestion(id: number): Question {
  return {
    id,
    content_revision: 1,
    content_schema_version: 2,
    content: richDoc(`题干${id}`),
    options: null,
    answer: null,
    thinking: richDoc(`思路${id}`),
    analysis: richDoc(`解析${id}`),
    summary: null,
    q_type: 'free_response',
    status: 'approved',
    difficulty: 3,
    source: 'seed',
  } as unknown as Question
}

const deps: ApplyDeps = {
  loadQuestions: async (ids) => ids.map(fakeQuestion),
}

/** 只有 loadQuestions 被调用时才记账，用来断言「写前重取」确实发生。 */
function trackingDeps(): ApplyDeps & { calls: number[][] } {
  const calls: number[][] = []
  return {
    calls,
    loadQuestions: async (ids) => {
      calls.push(ids)
      return ids.map(fakeQuestion)
    },
  }
}

function docOf(...nodes: EditorNode[]): EditorDocument {
  return normalizeDocument({ nodes })
}

function questionNode(id: number): EditorNode {
  return createQuestionNode(fakeQuestion(id))
}

function headingNode(text: string, level: 1 | 2 | 3 | 4 = 2): EditorNode {
  const node = createHeadingNode(level)
  node.content = headingTextToDoc(text)
  return node
}

async function run(doc: EditorDocument, ops: AiOperation[], d: ApplyDeps = deps) {
  return applyOperations(doc, ops, d)
}

// --------------------------------------------------------------------------- //
// insert_nodes
// --------------------------------------------------------------------------- //
describe('insert_nodes', () => {
  it('每个 Markdown 顶层块落成一个独立的 schema_version=2 节点', async () => {
    const { doc, results } = await run(docOf(), [{
      op: 'insert_nodes',
      after: 'end',
      nodes: [{ type: 'rich_text', rich_doc_blocks: [richDoc('第一段'), richDoc('第二段')] }],
    }])

    expect(results[0]!.ok).toBe(true)
    expect(doc.nodes).toHaveLength(2)
    expect(doc.nodes.every((n) => n.nodeType === 'rich_text' && n.schemaVersion === 2)).toBe(true)
  })

  it('after 指向节点 id 时插到它后面，start/end 落到两端', async () => {
    const a = headingNode('A')
    const b = headingNode('B')
    const { doc } = await run(docOf(a, b), [
      { op: 'insert_nodes', after: a.id, nodes: [{ type: 'page_break' }] },
      { op: 'insert_nodes', after: 'start', nodes: [{ type: 'heading', text: '封面', level: 1 }] },
      { op: 'insert_nodes', after: 'end', nodes: [{ type: 'answer_space', lines: 6, style: 'lined' }] },
    ])

    expect(doc.nodes.map((n) => n.nodeType)).toEqual([
      'heading', 'heading', 'page_break', 'heading', 'answer_space',
    ])
    expect(headingLevelOf(doc.nodes[0]!)).toBe(1)
  })

  it('question 节点的快照取自实时题目，而不是模型自己编的内容', async () => {
    const tracking = trackingDeps()
    const { doc } = await run(docOf(), [{
      op: 'insert_nodes',
      after: 'end',
      nodes: [{ type: 'question', question_id: 42, number: '3', score: 12 }],
    }], tracking)

    expect(tracking.calls).toEqual([[42]])
    const node = doc.nodes[0]!
    expect(node.questionId).toBe(42)
    expect(node.questionContent?.content).toEqual(richDoc('题干42'))
    expect(questionNumberOf(node)).toBe('3')
    expect(questionScoreOf(node)).toBe(12)
  })

  it('一批操作里的题目只取一次数', async () => {
    const tracking = trackingDeps()
    await run(docOf(), [
      { op: 'insert_nodes', after: 'end', nodes: [{ type: 'question', question_id: 1 }] },
      { op: 'insert_nodes', after: 'end', nodes: [{ type: 'question', question_id: 2 }] },
      { op: 'insert_nodes', after: 'end', nodes: [{ type: 'question', question_id: 1 }] },
    ], tracking)

    expect(tracking.calls).toEqual([[1, 2]])
  })

  it('题库里取不到的题目只让这一条失败，不影响其余操作', async () => {
    const { doc, results } = await run(docOf(), [
      { op: 'insert_nodes', after: 'end', nodes: [{ type: 'question', question_id: 7 }] },
      { op: 'insert_nodes', after: 'end', nodes: [{ type: 'page_break' }] },
    ], { loadQuestions: async () => [] })

    expect(results.map((r) => r.ok)).toEqual([false, true])
    expect(results[0]!.message).toContain('7')
    expect(doc.nodes.map((n) => n.nodeType)).toEqual(['page_break'])
  })

  it('锚点节点不存在时提示去重新读大纲', async () => {
    const { results } = await run(docOf(), [
      { op: 'insert_nodes', after: 'no-such-node', nodes: [{ type: 'page_break' }] },
    ])
    expect(results[0]!.ok).toBe(false)
    expect(results[0]!.message).toContain('read_composition_outline')
  })
})

// --------------------------------------------------------------------------- //
// remove_nodes / move_node
// --------------------------------------------------------------------------- //
describe('remove_nodes', () => {
  it('删题目时它派生的 answer_item 一并回收', async () => {
    const q1 = questionNode(1)
    const q2 = questionNode(2)
    const mod = createQuestionDetailsModule('all')
    const before = docOf(q1, q2, mod)
    expect(before.nodes[2]!.children).toHaveLength(2)

    const { doc } = await run(before, [{ op: 'remove_nodes', node_ids: [q1.id] }])
    expect(doc.nodes.map((n) => n.id)).toEqual([q2.id, mod.id])
    expect(doc.nodes[1]!.children).toHaveLength(1)
    expect(doc.nodes[1]!.children[0]!.sourceQuestionNodeId).toBe(q2.id)
  })

  it('拒绝单独删除模块内的派生节点（删了也会立刻长回来）', async () => {
    const q1 = questionNode(1)
    const mod = createQuestionDetailsModule('all')
    const before = docOf(q1, mod)
    const answerItemId = before.nodes[1]!.children[0]!.id

    const { doc, results } = await run(before, [{ op: 'remove_nodes', node_ids: [answerItemId] }])
    expect(results[0]!.ok).toBe(false)
    expect(results[0]!.message).toContain('派生节点')
    expect(doc.nodes[1]!.children).toHaveLength(1)
  })

  it('整条操作要么全删要么不删 —— 有一个 id 找不到就不删任何节点', async () => {
    const a = headingNode('A')
    const { doc, results } = await run(docOf(a), [
      { op: 'remove_nodes', node_ids: [a.id, 'ghost'] },
    ])
    expect(results[0]!.ok).toBe(false)
    expect(doc.nodes).toHaveLength(1)
  })
})

describe('move_node', () => {
  it('before 指定落点，省略则移到末尾', async () => {
    const a = headingNode('A')
    const b = headingNode('B')
    const c = headingNode('C')

    const moved = await run(docOf(a, b, c), [{ op: 'move_node', node_id: c.id, before: a.id }])
    expect(moved.doc.nodes.map((n) => n.id)).toEqual([c.id, a.id, b.id])

    const toEnd = await run(docOf(a, b, c), [{ op: 'move_node', node_id: a.id, before: null }])
    expect(toEnd.doc.nodes.map((n) => n.id)).toEqual([b.id, c.id, a.id])
  })

  it('不能移到自己之前', async () => {
    const a = headingNode('A')
    const { results } = await run(docOf(a), [{ op: 'move_node', node_id: a.id, before: a.id }])
    expect(results[0]!.ok).toBe(false)
  })
})

// --------------------------------------------------------------------------- //
// set_node_props
// --------------------------------------------------------------------------- //
describe('set_node_props', () => {
  it('按节点类型白名单放行，越界的属性名报错而不是静默忽略', async () => {
    const h = headingNode('A')
    const { doc, results } = await run(docOf(h), [
      { op: 'set_node_props', node_id: h.id, props: { level: 3 }, clear: [] },
      { op: 'set_node_props', node_id: h.id, props: { score: 5 }, clear: [] },
    ])

    expect(results[0]!.ok).toBe(true)
    expect(headingLevelOf(doc.nodes[0]!)).toBe(3)
    expect(results[1]!.ok).toBe(false)
    expect(results[1]!.message).toContain('score')
  })

  it('clear 能清掉题号与分值', async () => {
    const q = questionNode(1)
    const withProps = await run(docOf(q), [
      { op: 'set_node_props', node_id: q.id, props: { number: '5', score: 8 }, clear: [] },
    ])
    expect(questionScoreOf(withProps.doc.nodes[0]!)).toBe(8)

    const { doc } = await run(withProps.doc, [
      { op: 'set_node_props', node_id: q.id, props: {}, clear: ['score'] },
    ])
    expect(questionScoreOf(doc.nodes[0]!)).toBeNull()
    // 清分值不该顺手抹掉题号。
    expect(questionNumberOf(doc.nodes[0]!)).toBe('5')
  })

  it('改模块 scope 会立刻重新派生子节点', async () => {
    const q1 = questionNode(1)
    const mod = createQuestionDetailsModule('all')
    const q2 = questionNode(2)
    const before = docOf(q1, mod, q2)
    expect(before.nodes[1]!.children).toHaveLength(2)

    const { doc } = await run(before, [
      { op: 'set_node_props', node_id: mod.id, props: { scope: 'before' }, clear: [] },
    ])
    expect(detailPropsOf(doc.nodes[1]!).scope).toBe('before')
    expect(doc.nodes[1]!.children).toHaveLength(1)
  })

  it('模块内的子节点不接受直接修改', async () => {
    const q1 = questionNode(1)
    const mod = createQuestionDetailsModule('all')
    const before = docOf(q1, mod)
    const childId = before.nodes[1]!.children[0]!.id

    const { results } = await run(before, [
      { op: 'set_node_props', node_id: childId, props: { score: 1 }, clear: [] },
    ])
    expect(results[0]!.ok).toBe(false)
    expect(results[0]!.message).toContain('参考答案模块')
  })

  it('作答空间只改给定的那一项', async () => {
    const space = createAnswerSpaceNode(3, 'blank')
    const { doc } = await run(docOf(space), [
      { op: 'set_node_props', node_id: space.id, props: { lines: 8 }, clear: [] },
    ])
    expect(doc.nodes[0]!.props).toEqual({ lines: 8, style: 'blank' })
  })
})

// --------------------------------------------------------------------------- //
// show_question_fields / add_details_module
// --------------------------------------------------------------------------- //
describe('show_question_fields', () => {
  it('三态：show / hide / inherit（inherit 回落到稿件全局开关）', async () => {
    const q = questionNode(1)
    const shown = await run(docOf(q), [
      { op: 'show_question_fields', node_id: q.id, show: { thinking: 'show', analysis: 'hide' } },
    ])
    expect(questionShowOverride(shown.doc.nodes[0]!, 'thinking')).toBe(true)
    expect(questionShowOverride(shown.doc.nodes[0]!, 'analysis')).toBe(false)

    const { doc } = await run(shown.doc, [
      { op: 'show_question_fields', node_id: q.id, show: { thinking: 'inherit' } },
    ])
    expect(questionShowOverride(doc.nodes[0]!, 'thinking')).toBeNull()
    // 只动指定的字段。
    expect(questionShowOverride(doc.nodes[0]!, 'analysis')).toBe(false)
  })

  it('目标不是题目时报错', async () => {
    const h = headingNode('A')
    const { results } = await run(docOf(h), [
      { op: 'show_question_fields', node_id: h.id, show: { answer: 'show' } },
    ])
    expect(results[0]!.ok).toBe(false)
    expect(results[0]!.message).toContain('不是题目')
  })
})

describe('add_details_module', () => {
  it('标题写成模块前的同级块，answer_item 由规范化派生', async () => {
    const q1 = questionNode(1)
    const q2 = questionNode(2)
    const { doc } = await run(docOf(q1, q2), [{
      op: 'add_details_module',
      after: 'end',
      scope: 'all',
      fields: { answer: true, thinking: false, analysis: true, summary: false },
      title: '参考答案',
    }])

    expect(doc.nodes.map((n) => n.nodeType)).toEqual(['question', 'question', 'heading', 'question_details'])
    const mod = doc.nodes[3]!
    expect(detailPropsOf(mod).fields).toEqual({
      answer: true, thinking: false, analysis: true, summary: false,
    })
    expect(mod.children.map((c) => c.sourceQuestionNodeId)).toEqual([q1.id, q2.id])
  })
})

// --------------------------------------------------------------------------- //
// 批次语义
// --------------------------------------------------------------------------- //
describe('批次语义', () => {
  it('后一条操作看得到前一条的结果', async () => {
    const q = questionNode(1)
    const { doc, results } = await run(docOf(q), [
      { op: 'insert_nodes', after: q.id, nodes: [{ type: 'heading', text: '二、解答题', level: 2 }] },
      { op: 'set_node_props', node_id: q.id, props: { number: '1' }, clear: [] },
    ])
    expect(results.every((r) => r.ok)).toBe(true)
    expect(doc.nodes.map((n) => n.nodeType)).toEqual(['question', 'heading'])
    expect(questionNumberOf(doc.nodes[0]!)).toBe('1')
  })

  it('不修改入参文档', async () => {
    const q = questionNode(1)
    const before = docOf(q)
    const snapshot = JSON.stringify(before)
    await run(before, [{ op: 'remove_nodes', node_ids: [q.id] }])
    expect(JSON.stringify(before)).toBe(snapshot)
  })

  it('不认识的操作名单条失败，不抛出去打断整批', async () => {
    const { results } = await run(docOf(), [
      { op: 'wrap_in_module', node_ids: ['a'] } as unknown as AiOperation,
    ])
    expect(results[0]!.ok).toBe(false)
    expect(results[0]!.message).toContain('wrap_in_module')
  })
})

describe('纯结构节点', () => {
  it('rich_text 节点用画布同源的单块形态', async () => {
    const node = createRichTextNode()
    expect(node.nodeType).toBe('rich_text')
  })
})
