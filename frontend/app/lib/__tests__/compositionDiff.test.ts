import { describe, it, expect } from 'vitest'
import {
  createAnswerSpaceNode,
  createHeadingNode,
  createQuestionDetailsModule,
  createQuestionNode,
  headingTextToDoc,
  normalizeDocument,
} from '@/lib/compositionDocument'
import type { EditorDocument, EditorNode } from '@/lib/compositionDocument'
import { diffDocuments } from '@/lib/compositionDiff'
import { applyOperations } from '@/lib/compositionPrimitives'
import type { ApplyDeps } from '@/lib/compositionPrimitives'
import type { Question } from '@/types'

function richDoc(text: string) {
  return { type: 'doc' as const, content: [{ type: 'paragraph', content: [{ type: 'text', text }] }] }
}

function fakeQuestion(id: number): Question {
  return {
    id,
    content_revision: 1,
    content_schema_version: 2,
    content: richDoc(`求 f(x)=x^2 的最小值 ${id}`),
    options: null,
    answer: null,
    thinking: null,
    analysis: null,
    summary: null,
    q_type: 'free_response',
    status: 'approved',
    difficulty: 3,
    source: 'seed',
  } as unknown as Question
}

const deps: ApplyDeps = { loadQuestions: async (ids) => ids.map(fakeQuestion) }

function docOf(...nodes: EditorNode[]): EditorDocument {
  return normalizeDocument({ nodes })
}

function headingNode(text: string): EditorNode {
  const node = createHeadingNode(2)
  node.content = headingTextToDoc(text)
  return node
}

describe('diffDocuments', () => {
  it('没有改动时清单为空', () => {
    const doc = docOf(headingNode('A'), createQuestionNode(fakeQuestion(1)))
    expect(diffDocuments(doc, doc)).toEqual([])
  })

  it('新增与删除各记一条，且带得出人话描述', async () => {
    const h = headingNode('一、选择题')
    const before = docOf(h)
    const { doc: after } = await applyOperations(before, [
      { op: 'remove_nodes', node_ids: [h.id] },
      { op: 'insert_nodes', after: 'end', nodes: [{ type: 'question', question_id: 9 }] },
    ], deps)

    const changes = diffDocuments(before, after)
    expect(changes.map((c) => c.kind).sort()).toEqual(['added', 'removed'])
    expect(changes.find((c) => c.kind === 'removed')!.label).toContain('一、选择题')
    expect(changes.find((c) => c.kind === 'added')!.label).toContain('求 f(x)=x^2')
  })

  it('改属性记成 modified，并说清改了什么', async () => {
    const q = createQuestionNode(fakeQuestion(1))
    const before = docOf(q)
    const { doc: after } = await applyOperations(before, [
      { op: 'set_node_props', node_id: q.id, props: { number: '3', score: 12 }, clear: [] },
      { op: 'show_question_fields', node_id: q.id, show: { analysis: 'show' } },
    ], deps)

    const changes = diffDocuments(before, after)
    expect(changes).toHaveLength(1)
    expect(changes[0]!.kind).toBe('modified')
    expect(changes[0]!.label).toContain('题号 无 → 3')
    expect(changes[0]!.label).toContain('分值 无 → 12')
    expect(changes[0]!.label).toContain('解析显示')
  })

  it('只换位置记成 moved，且只标出真正动了的那一个', async () => {
    const a = headingNode('A')
    const b = headingNode('B')
    const c = headingNode('C')
    const before = docOf(a, b, c)
    const { doc: after } = await applyOperations(before, [
      { op: 'move_node', node_id: c.id, before: a.id },
    ], deps)

    // a/b 的相对顺序没变，清单不应该把它俩也算成“被移动”。
    const changes = diffDocuments(before, after)
    expect(changes).toHaveLength(1)
    expect(changes[0]!.kind).toBe('moved')
    expect(changes[0]!.nodeId).toBe(c.id)
  })

  it('answer_item 是派生节点，不单独进清单', async () => {
    const q1 = createQuestionNode(fakeQuestion(1))
    const mod = createQuestionDetailsModule('all')
    const before = docOf(q1, mod)
    const { doc: after } = await applyOperations(before, [
      { op: 'insert_nodes', after: q1.id, nodes: [{ type: 'question', question_id: 2 }] },
    ], deps)

    // 模块里多了一条 answer_item，但用户看到的只是「新增了一道题」。
    expect(after.nodes[2]!.children).toHaveLength(2)
    const changes = diffDocuments(before, after)
    expect(changes).toHaveLength(1)
    expect(changes[0]!.kind).toBe('added')
  })

  it('模块自身的字段调整能说出来', async () => {
    const q = createQuestionNode(fakeQuestion(1))
    const mod = createQuestionDetailsModule('all')
    const before = docOf(q, mod)
    const { doc: after } = await applyOperations(before, [{
      op: 'set_node_props',
      node_id: mod.id,
      props: { fields: { answer: true, thinking: false, analysis: true, summary: false } },
      clear: [],
    }], deps)

    const changes = diffDocuments(before, after)
    expect(changes[0]!.label).toContain('展示字段调整')
    expect(changes[0]!.label).toContain('解析')
  })

  it('长文本摘要会截断，不把整段正文塞进清单', async () => {
    const long = headingNode('这是一个非常非常长的标题'.repeat(10))
    const before = docOf()
    const after = docOf(long)
    const label = diffDocuments(before, after)[0]!.label
    expect(label.length).toBeLessThan(80)
    expect(label).toContain('…')
  })

  it('作答空间的行数变化说得出来', async () => {
    const space = createAnswerSpaceNode(3, 'blank')
    const before = docOf(space)
    const { doc: after } = await applyOperations(before, [
      { op: 'set_node_props', node_id: space.id, props: { lines: 8 }, clear: [] },
    ], deps)
    expect(diffDocuments(before, after)[0]!.label).toContain('行数 3 → 8')
  })
})
