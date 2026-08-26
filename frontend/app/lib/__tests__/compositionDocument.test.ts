import { describe, it, expect } from 'vitest'
import {
  answerItemPropsOf,
  collectDocumentIssues,
  collectStaleQuestionNodeIds,
  createHeadingNode,
  createPageBreakNode,
  createQuestionDetailsModule,
  createQuestionNode,
  createRichTextNode,
  DETAIL_PRESETS,
  detailPropsOf,
  documentFromNodes,
  documentToReplaceRequest,
  effectiveQuestionField,
  generateNodeId,
  hasAnyQuestionNumber,
  applyQuestionNumbers,
  headingDocToText,
  headingHasRichInline,
  headingTextToDoc,
  insertModuleCustomBefore,
  insertRootNodeAfter,
  moveRootNode,
  normalizeDocument,
  patchNode,
  questionNodeStatus,
  questionNumberOf,
  questionOptionLayoutOf,
  questionPropsWithOptionLayout,
  questionPropsWithShow,
  questionShowOverride,
  removeRootNode,
  resolveOptionColumns,
  snapshotDocument,
} from '@/lib/compositionDocument'
import type { EditorDocument, EditorNode } from '@/lib/compositionDocument'
import type { CompositionNode, QuestionRevisionStatus } from '@/types/composition'
import type { Question } from '@/types'

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

function richDoc(text: string) {
  return { type: 'doc' as const, content: [{ type: 'paragraph', content: [{ type: 'text', text }] }] }
}

function fakeQuestion(id: number, revision = 1): Question {
  return {
    id,
    content_revision: revision,
    content_schema_version: 2,
    content: richDoc(`题干${id}`),
    options: [{ id: 'opt_a', label: 'A', content: richDoc('A') }],
    answer: { kind: 'single_choice', correct: 'opt_a' },
    thinking: null,
    analysis: richDoc(`解析${id}`),
    summary: null,
    q_type: 'single_choice',
    status: 'approved',
    difficulty: 3,
    knowledge_points: [],
    tags: [],
    created_at: '',
    updated_at: '',
    review_count: 0,
    source: 'seed',
  } as unknown as Question
}

function doc(nodes: EditorNode[]): EditorDocument {
  return normalizeDocument({ nodes })
}

describe('UUID 创建', () => {
  it('generateNodeId 产出合法且唯一的 v4 UUID', () => {
    const ids = Array.from({ length: 100 }, () => generateNodeId())
    expect(new Set(ids).size).toBe(100)
    ids.forEach((id) => expect(id).toMatch(UUID_RE))
  })

  it('工厂节点 id 均为合法 UUID', () => {
    expect(createRichTextNode().id).toMatch(UUID_RE)
    expect(createHeadingNode().id).toMatch(UUID_RE)
    expect(createQuestionNode(fakeQuestion(1)).id).toMatch(UUID_RE)
  })
})

describe('根节点工厂与预设', () => {
  it('各类型默认值合理', () => {
    expect(createRichTextNode().content).toEqual({ type: 'doc', content: [{ type: 'paragraph' }] })
    expect(detailPropsOf(createHeadingNode()).scope).toBeUndefined()
    expect(createHeadingNode(3).props).toEqual({ level: 3 })
    expect(createPageBreakNode().content).toBeNull()
    const q = createQuestionNode(fakeQuestion(7, 4))
    expect(q.questionId).toBe(7)
    expect(q.questionRevision).toBe(4)
    expect(q.questionContent?.q_type).toBe('single_choice')
  })

  it('汇总模块预设：默认仅答案、标题「参考答案」', () => {
    const summary = DETAIL_PRESETS.summary()
    expect(detailPropsOf(summary).fields).toEqual({
      answer: true, thinking: false, analysis: false, summary: false,
    })
    expect(headingDocToText(summary.children[0]!.content)).toBe('参考答案')
  })
})

describe('规范化 answer_item（scope=all / before）', () => {
  it('scope=all 为整篇每个 question 节点产出一条 answer_item', () => {
    const q1 = createQuestionNode(fakeQuestion(1))
    const q2 = createQuestionNode(fakeQuestion(2))
    const mod = createQuestionDetailsModule('all')
    const d = doc([q1, q2, mod])
    const module = d.nodes[2]!
    expect(module.children.map((c) => c.sourceQuestionNodeId)).toEqual([q1.id, q2.id])
    expect(module.children.every((c) => c.nodeType === 'answer_item')).toBe(true)
  })

  it('scope=before 只汇总 module 之前的 question 节点', () => {
    const q1 = createQuestionNode(fakeQuestion(1))
    const mod = createQuestionDetailsModule('before')
    const q2 = createQuestionNode(fakeQuestion(2))
    const d = doc([q1, mod, q2])
    const module = d.nodes[1]!
    expect(module.children.map((c) => c.sourceQuestionNodeId)).toEqual([q1.id])
  })

  it('重复 question_id 因 question 节点 UUID 不同而各自保留 answer_item', () => {
    const qa = createQuestionNode(fakeQuestion(5))
    const qb = createQuestionNode(fakeQuestion(5))
    const mod = createQuestionDetailsModule('all')
    const d = doc([qa, qb, mod])
    const module = d.nodes[2]!
    expect(module.children).toHaveLength(2)
    expect(module.children.map((c) => c.sourceQuestionNodeId)).toEqual([qa.id, qb.id])
  })

  it('再规范化保留已有 answer_item 的 id 与配置（included/overrides）', () => {
    const q1 = createQuestionNode(fakeQuestion(1))
    const mod = createQuestionDetailsModule('all')
    let d = doc([q1, mod])
    const ai = d.nodes[1]!.children[0]!
    // 用户改配置。
    d = patchNode(d, ai.id, { props: { included: false, overrides: { answer: true, thinking: null, analysis: null, summary: null } } })
    // 触发再规范化（插入无关节点）。
    d = insertRootNodeAfter(d, 0, createPageBreakNode())
    const again = d.nodes.find((n) => n.nodeType === 'question_details')!.children[0]!
    expect(again.id).toBe(ai.id)
    expect(answerItemPropsOf(again).included).toBe(false)
    expect(answerItemPropsOf(again).overrides.answer).toBe(true)
  })

  it('自定义 heading/rich_text 依 anchor 排在指定 answer_item 之前', () => {
    const q1 = createQuestionNode(fakeQuestion(1))
    const q2 = createQuestionNode(fakeQuestion(2))
    const mod = createQuestionDetailsModule('all')
    let d = doc([q1, q2, mod])
    const secondAi = d.nodes[2]!.children[1]!
    const heading = createHeadingNode()
    heading.content = richDoc('小节')
    d = insertModuleCustomBefore(d, mod.id, secondAi.id, heading)
    const kids = d.nodes.find((n) => n.id === mod.id)!.children
    const headingIdx = kids.findIndex((c) => c.nodeType === 'heading')
    const secondIdx = kids.findIndex((c) => c.id === secondAi.id)
    expect(headingIdx).toBeGreaterThanOrEqual(0)
    expect(headingIdx).toBe(secondIdx - 1)
  })

  it('无题目时也能在模块尾部插入自定义内容', () => {
    const mod = createQuestionDetailsModule('all')
    const text = createRichTextNode()
    text.content = richDoc('使用说明')
    const d = insertModuleCustomBefore(doc([mod]), mod.id, null, text)
    const children = d.nodes[0]!.children
    expect(children).toHaveLength(1)
    expect(children[0]!.nodeType).toBe('rich_text')
    expect(children[0]!.anchorBeforeNodeId).toBeNull()
  })

  it('未锚定且位于 answer_item 之前的自定义节点置顶', () => {
    const q1 = createQuestionNode(fakeQuestion(1))
    const q2 = createQuestionNode(fakeQuestion(2))
    const mod = createQuestionDetailsModule('all')
    const heading = createHeadingNode(2)
    heading.content = richDoc('参考答案')
    // 预设写法：标题作为模块首个子节点、无锚点。
    mod.children = [heading]
    const d = doc([q1, q2, mod])
    const kids = d.nodes.find((n) => n.id === mod.id)!.children
    expect(kids[0]!.nodeType).toBe('heading')
    expect(kids[0]!.anchorBeforeNodeId).toBeNull()
    expect(kids.slice(1).every((c) => c.nodeType === 'answer_item')).toBe(true)
  })
})

describe('序列化 documentToReplaceRequest', () => {
  it('root 先 module 子后；question 不带 content，module 子带 parent/slot', () => {
    const q1 = createQuestionNode(fakeQuestion(1))
    const mod = createQuestionDetailsModule('all')
    const d = doc([q1, mod])
    const req = documentToReplaceRequest(d, 3, 'batch-1')
    expect(req.expected_revision).toBe(3)
    expect(req.batch_id).toBe('batch-1')
    // nodes: question(root), module(root), answer_item(child)
    const [qNode, modNode, aiNode] = req.nodes
    expect(qNode!.node_type).toBe('question')
    expect(qNode!.content).toBeUndefined()
    expect(qNode!.question_id).toBe(1)
    expect(qNode!.parent_id).toBeUndefined()
    expect(modNode!.node_type).toBe('question_details')
    expect(aiNode!.node_type).toBe('answer_item')
    expect(aiNode!.parent_id).toBe(mod.id)
    expect(aiNode!.slot).toBe('body')
    expect(aiNode!.source_question_node_id).toBe(q1.id)
  })

  it('无 batchId 时不带 batch_id', () => {
    const req = documentToReplaceRequest(doc([createPageBreakNode()]), 1)
    expect(req.batch_id).toBeUndefined()
  })
})

describe('题号填充 applyQuestionNumbers / hasAnyQuestionNumber', () => {
  it('global 模式按顺序 1,2,3…（跳过非题目节点）', () => {
    const q1 = createQuestionNode(fakeQuestion(1))
    const q2 = createQuestionNode(fakeQuestion(2))
    const q3 = createQuestionNode(fakeQuestion(3))
    const d = doc([q1, createHeadingNode(2), q2, createPageBreakNode(), q3])
    const out = applyQuestionNumbers(d, 'global')
    const numbers = out.nodes.filter((n) => n.nodeType === 'question').map(questionNumberOf)
    expect(numbers).toEqual(['1', '2', '3'])
  })

  it('heading 模式以 H2 分组，组内 g.n；H1 不分组，首个 H2 前归第 1 组', () => {
    const h1 = createHeadingNode(1)
    const q1 = createQuestionNode(fakeQuestion(1))
    const h2a = createHeadingNode(2)
    const q2 = createQuestionNode(fakeQuestion(2))
    const q3 = createQuestionNode(fakeQuestion(3))
    const h2b = createHeadingNode(2)
    const q4 = createQuestionNode(fakeQuestion(4))
    const d = doc([h1, q1, h2a, q2, q3, h2b, q4])
    const out = applyQuestionNumbers(d, 'heading')
    const numbers = out.nodes.filter((n) => n.nodeType === 'question').map(questionNumberOf)
    expect(numbers).toEqual(['1.1', '2.1', '2.2', '3.1'])
  })

  it('heading 模式跳过空组（连续 H2 无题目）', () => {
    const q1 = createQuestionNode(fakeQuestion(1))
    const q2 = createQuestionNode(fakeQuestion(2))
    const d = doc([q1, createHeadingNode(2), createHeadingNode(2), q2])
    const out = applyQuestionNumbers(d, 'heading')
    const numbers = out.nodes.filter((n) => n.nodeType === 'question').map(questionNumberOf)
    expect(numbers).toEqual(['1.1', '2.1'])
  })

  it('填充结果覆盖已有，且 hasAnyQuestionNumber 反映状态', () => {
    const q1 = createQuestionNode(fakeQuestion(1))
    const d = doc([q1])
    expect(hasAnyQuestionNumber(d)).toBe(false)
    const filled = applyQuestionNumbers(d, 'global')
    expect(hasAnyQuestionNumber(filled)).toBe(true)
    expect(questionNumberOf(filled.nodes[0]!)).toBe('1')
  })

  it('题号随 question 节点序列化进 props', () => {
    const q1 = createQuestionNode(fakeQuestion(1))
    const filled = applyQuestionNumbers(doc([q1]), 'global')
    const req = documentToReplaceRequest(filled, 1)
    const qNode = req.nodes.find((n) => n.node_type === 'question')
    expect(qNode!.props).toEqual({ number: '1' })
  })
})

describe('题目字段显隐（全局 + 题目级覆盖）', () => {
  const global = { answer: true, thinking: false, analysis: false, summary: false }

  it('无覆盖时跟随全局；override 优先', () => {
    const q = createQuestionNode(fakeQuestion(1))
    expect(effectiveQuestionField(q, global, 'answer')).toBe(true)
    expect(effectiveQuestionField(q, global, 'analysis')).toBe(false)
    expect(questionShowOverride(q, 'answer')).toBeNull()

    const hidden = { ...q, props: questionPropsWithShow(q, 'answer', false) }
    expect(questionShowOverride(hidden, 'answer')).toBe(false)
    expect(effectiveQuestionField(hidden, global, 'answer')).toBe(false)

    const shown = { ...q, props: questionPropsWithShow(q, 'analysis', true) }
    expect(effectiveQuestionField(shown, global, 'analysis')).toBe(true)
  })

  it('questionPropsWithShow 保留 number，继承时清除覆盖', () => {
    const q = createQuestionNode(fakeQuestion(1))
    q.props = { number: '3' }
    const withHide = questionPropsWithShow(q, 'answer', false)
    expect(withHide).toEqual({ number: '3', show: { answer: false } })
    const back = questionPropsWithShow({ ...q, props: withHide }, 'answer', null)
    expect(back).toEqual({ number: '3' })
  })

  it('show 覆盖序列化进 props.show（只包含显式布尔）', () => {
    const q = createQuestionNode(fakeQuestion(1))
    q.props = questionPropsWithShow(q, 'thinking', true)
    const req = documentToReplaceRequest(doc([q]), 1)
    const qNode = req.nodes.find((n) => n.node_type === 'question')
    expect(qNode!.props).toEqual({ show: { thinking: true } })
  })
})

describe('documentFromNodes 重建（含 module 子树）', () => {
  it('按 position 排序并挂接 module 子节点', () => {
    const server: CompositionNode[] = [
      { id: 'm1', composition_id: 9, parent_id: null, slot: null, position: 1, node_kind: 'module', node_type: 'question_details', content: null, props: { scope: 'all', fields: { answer: true, thinking: false, analysis: false, summary: false } }, schema_version: 1, question_id: null, question_revision: null, source_question_node_id: null, anchor_before_node_id: null } as CompositionNode,
      { id: 'q1', composition_id: 9, parent_id: null, slot: null, position: 0, node_kind: 'block', node_type: 'question', content: { content_schema_version: 2, q_type: 'single_choice', content: richDoc('题'), options: null, answer: null, thinking: null, analysis: null, summary: null, difficulty: 1, source: null }, props: null, schema_version: 1, question_id: 1, question_revision: 2, source_question_node_id: null, anchor_before_node_id: null } as CompositionNode,
      { id: 'ai1', composition_id: 9, parent_id: 'm1', slot: 'body', position: 0, node_kind: 'reference', node_type: 'answer_item', content: null, props: { included: true, overrides: { answer: null, thinking: null, analysis: null, summary: null } }, schema_version: 1, question_id: null, question_revision: null, source_question_node_id: 'q1', anchor_before_node_id: null } as CompositionNode,
    ]
    const d = documentFromNodes(server)
    expect(d.nodes.map((n) => n.id)).toEqual(['q1', 'm1'])
    expect(d.nodes[0]!.questionContent?.q_type).toBe('single_choice')
    expect(d.nodes[1]!.children.map((c) => c.id)).toEqual(['ai1'])
  })
})

describe('root 层编辑操作', () => {
  it('moveRootNode 交换相邻，越界返回原序', () => {
    const a = createPageBreakNode(); const b = createRichTextNode(); const c = createPageBreakNode()
    b.content = richDoc('x')
    const d = doc([a, b, c])
    expect(moveRootNode(d, 0, 'down').nodes.map((n) => n.id)).toEqual([b.id, a.id, c.id])
    expect(moveRootNode(d, 0, 'up').nodes.map((n) => n.id)).toEqual([a.id, b.id, c.id])
  })

  it('removeRootNode 删除根节点', () => {
    const a = createPageBreakNode(); const b = createPageBreakNode()
    const d = doc([a, b])
    expect(removeRootNode(d, a.id).nodes.map((n) => n.id)).toEqual([b.id])
  })
})

describe('脏检测与保存校验', () => {
  it('snapshotDocument 忽略 id / questionRevision / questionContent', () => {
    const q1 = createQuestionNode(fakeQuestion(1, 2))
    const s1 = snapshotDocument(doc([q1]))
    const q1b = createQuestionNode(fakeQuestion(1, 9))
    const s2 = snapshotDocument(doc([q1b]))
    expect(s1).toBe(s2)
  })

  it('内容变化改变快照', () => {
    const a = createRichTextNode(); a.content = richDoc('x')
    const b = createRichTextNode(); b.content = richDoc('y')
    expect(snapshotDocument(doc([a]))).not.toBe(snapshotDocument(doc([b])))
  })

  it('保存后快照稳定：由服务端响应重建应与保存前一致', () => {
    const q1 = createQuestionNode(fakeQuestion(1))
    const mod = createQuestionDetailsModule('all')
    const before = doc([q1, mod])
    const req = documentToReplaceRequest(before, 1)
    // 模拟服务端把请求 nodes 落库后回读（补齐 position/composition_id）。
    const server: CompositionNode[] = req.nodes.map((n, i) => ({
      id: n.id,
      composition_id: 9,
      parent_id: n.parent_id ?? null,
      slot: n.slot ?? null,
      position: i,
      node_kind: n.node_kind,
      node_type: n.node_type,
      content: n.node_type === 'question' ? { content_schema_version: 2, q_type: 'single_choice', content: richDoc('题干1'), options: null, answer: null, thinking: null, analysis: null, summary: null, difficulty: 1, source: null } : (n.content ?? null),
      props: n.props ?? null,
      schema_version: 1,
      question_id: n.question_id ?? null,
      question_revision: n.node_type === 'question' ? 1 : null,
      source_question_node_id: n.source_question_node_id ?? null,
      anchor_before_node_id: n.anchor_before_node_id ?? null,
    })) as CompositionNode[]
    const after = documentFromNodes(server)
    expect(snapshotDocument(after)).toBe(snapshotDocument(before))
  })

  it('collectDocumentIssues 标记空文本/空标题/缺题', () => {
    const empty = createRichTextNode(); empty.content = { type: 'doc', content: [{ type: 'paragraph' }] }
    const emptyHeading = createHeadingNode()
    const q = createQuestionNode(fakeQuestion(1)); q.questionId = null
    const issues = collectDocumentIssues(doc([empty, emptyHeading, q]))
    expect(issues).toHaveLength(3)
  })
})

describe('question 节点版本状态', () => {
  it('questionNodeStatus 计算 stale / deleted', () => {
    const q = createQuestionNode(fakeQuestion(1, 2))
    expect(questionNodeStatus(q, { question_id: 1, current_revision: 5, available: true })).toEqual({ stale: true, deleted: false })
    expect(questionNodeStatus(q, { question_id: 1, current_revision: 2, available: true })).toEqual({ stale: false, deleted: false })
    expect(questionNodeStatus(q, { question_id: 1, current_revision: null, available: false })).toEqual({ stale: false, deleted: true })
  })

  it('collectStaleQuestionNodeIds 返回过期 question 节点 UUID', () => {
    const q1 = createQuestionNode(fakeQuestion(1, 1))
    const q2 = createQuestionNode(fakeQuestion(2, 3))
    const d = doc([q1, q2])
    const map = new Map<number, QuestionRevisionStatus>([
      [1, { question_id: 1, current_revision: 5, available: true }],
      [2, { question_id: 2, current_revision: 3, available: true }],
    ])
    expect(collectStaleQuestionNodeIds(d, map)).toEqual([q1.id])
  })
})

describe('heading 富文本转换', () => {
  it('纯文本 <-> 单段落 RichDoc 往返', () => {
    const d = headingTextToDoc('第一章')
    expect(d).toEqual(richDoc('第一章'))
    expect(headingDocToText(d)).toBe('第一章')
    expect(headingDocToText(headingTextToDoc(''))).toBe('')
  })

  it('headingHasRichInline 检测非文本行内节点', () => {
    const withMath = { type: 'doc' as const, content: [{ type: 'paragraph', content: [{ type: 'inlineMath', attrs: { latex: 'x^2' } }] }] }
    expect(headingHasRichInline(withMath)).toBe(true)
    expect(headingHasRichInline(richDoc('纯文本'))).toBe(false)
  })
})

describe('选项排版', () => {
  const opts = (...texts: string[]) => texts.map((t, i) => ({ id: `opt_${i}`, label: String(i), content: richDoc(t) }))

  it('auto 按最长选项文本长度选列数', () => {
    expect(resolveOptionColumns(opts('12', '11', '8', '6'), 'auto')).toBe(4)
    expect(resolveOptionColumns(opts('十二个字的选项', 'B', 'C', 'D'), 'auto')).toBe(2)
    expect(resolveOptionColumns(opts('这是一个非常长的选项文本足够超过阈值了', 'B'), 'auto')).toBe(1)
  })

  it('auto 含图片/表格/块公式强制单列', () => {
    const withImage = [{ id: 'a', label: 'A', content: { type: 'doc' as const, content: [{ type: 'image', attrs: { src: 'x' } }] } }, { id: 'b', label: 'B', content: richDoc('B') }]
    expect(resolveOptionColumns(withImage, 'auto')).toBe(1)
  })

  it('固定列数按选项数收窄', () => {
    expect(resolveOptionColumns(opts('A', 'B', 'C', 'D'), 2)).toBe(2)
    expect(resolveOptionColumns(opts('A', 'B'), 4)).toBe(2)
    expect(resolveOptionColumns([], 4)).toBe(1)
  })

  it('questionOptionLayoutOf 读取与写入 props', () => {
    const node = createQuestionNode(fakeQuestion(1))
    expect(questionOptionLayoutOf(node)).toBe('auto')
    node.props = questionPropsWithOptionLayout(node, 4)
    expect(questionOptionLayoutOf(node)).toBe(4)
    node.props = questionPropsWithOptionLayout(node, 'auto')
    expect(questionOptionLayoutOf(node)).toBe('auto')
  })
})
