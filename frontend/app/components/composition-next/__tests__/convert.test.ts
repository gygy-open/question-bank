import { describe, it, expect } from 'vitest'
import { editorDocumentToPmDoc, pmDocToEditorDocument } from '../convert'
import type { EditorDocument, EditorNode } from '@/lib/compositionDocument'

function richTextRow(id: string, text: string): EditorNode {
  return {
    id,
    nodeType: 'rich_text',
    content: { type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text }] }] },
    props: null,
    questionId: null,
    questionRevision: null,
    questionContent: null,
    sourceQuestionNodeId: null,
    anchorBeforeNodeId: null,
    schemaVersion: 2,
    children: [],
  }
}

function headingRow(id: string, level: 1 | 2 | 3 | 4, text: string): EditorNode {
  return {
    id,
    nodeType: 'heading',
    content: { type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text }] }] },
    props: { level },
    questionId: null,
    questionRevision: null,
    questionContent: null,
    sourceQuestionNodeId: null,
    anchorBeforeNodeId: null,
    children: [],
  }
}

function questionRow(id: string, questionId: number): EditorNode {
  return {
    id,
    nodeType: 'question',
    content: null,
    props: { number: '1' },
    questionId,
    questionRevision: 3,
    questionContent: {
      content_schema_version: 2,
      q_type: 'single_choice',
      content: { type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text: 'Q' }] }] },
      options: null,
      answer: null,
      thinking: null,
      analysis: null,
      summary: null,
      difficulty: 3,
      source: null,
    },
    sourceQuestionNodeId: null,
    anchorBeforeNodeId: null,
    children: [],
  } as EditorNode
}

function pageBreakRow(id: string): EditorNode {
  return {
    id,
    nodeType: 'page_break',
    content: null,
    props: null,
    questionId: null,
    questionRevision: null,
    questionContent: null,
    sourceQuestionNodeId: null,
    anchorBeforeNodeId: null,
    children: [],
  }
}

function answerSpaceRow(id: string, lines = 3, style: 'blank' | 'lined' = 'blank'): EditorNode {
  return {
    id,
    nodeType: 'answer_space',
    content: null,
    props: { lines, style },
    questionId: null,
    questionRevision: null,
    questionContent: null,
    sourceQuestionNodeId: null,
    anchorBeforeNodeId: null,
    children: [],
  }
}

function moduleRow(id: string): EditorNode {
  return {
    id,
    nodeType: 'question_details',
    content: null,
    props: { scope: 'all', fields: { answer: true, thinking: false, analysis: false, summary: false } },
    questionId: null,
    questionRevision: null,
    questionContent: null,
    sourceQuestionNodeId: null,
    anchorBeforeNodeId: null,
    children: [headingRow('c1', 2, '参考答案')],
  }
}

describe('composition-next convert round-trip', () => {
  it('rich_text single block preserves row id and content', () => {
    const doc: EditorDocument = { nodes: [richTextRow('r1', 'hello')] }
    const back = pmDocToEditorDocument(editorDocumentToPmDoc(doc))
    expect(back).toEqual(doc)
  })

  it('heading preserves id, level and text', () => {
    const doc: EditorDocument = { nodes: [headingRow('h1', 3, 'Title')] }
    const back = pmDocToEditorDocument(editorDocumentToPmDoc(doc))
    expect(back.nodes[0]!.id).toBe('h1')
    expect(back.nodes[0]!.nodeType).toBe('heading')
    expect(back.nodes[0]!.props).toEqual({ level: 3 })
    expect(back.nodes[0]!.content?.content?.[0]?.content?.[0]).toEqual({ type: 'text', text: 'Title' })
  })

  it('question atom preserves snapshot and props', () => {
    const doc: EditorDocument = { nodes: [questionRow('q1', 42)] }
    const back = pmDocToEditorDocument(editorDocumentToPmDoc(doc))
    expect(back.nodes[0]!.id).toBe('q1')
    expect(back.nodes[0]!.questionId).toBe(42)
    expect(back.nodes[0]!.questionRevision).toBe(3)
    expect(back.nodes[0]!.props).toEqual({ number: '1' })
    expect(back.nodes[0]!.questionContent?.q_type).toBe('single_choice')
  })

  it('page_break survives losslessly', () => {
    const doc: EditorDocument = { nodes: [pageBreakRow('p1')] }
    const back = pmDocToEditorDocument(editorDocumentToPmDoc(doc))
    expect(back.nodes[0]).toEqual(pageBreakRow('p1'))
  })

  it('answer_space survives losslessly with lines and style', () => {
    const doc: EditorDocument = { nodes: [answerSpaceRow('a1', 6, 'lined')] }
    const back = pmDocToEditorDocument(editorDocumentToPmDoc(doc))
    expect(back.nodes[0]).toEqual(answerSpaceRow('a1', 6, 'lined'))
  })

  it('module lifts custom heading out and becomes a childless atom', () => {
    const doc: EditorDocument = { nodes: [moduleRow('m1')] }
    const back = pmDocToEditorDocument(editorDocumentToPmDoc(doc))
    // 自定义标题上提为模块前的顶层块；模块只剩 props、children 为空。
    expect(back.nodes.map((n) => n.nodeType)).toEqual(['heading', 'question_details'])
    expect(back.nodes[0]!.id).toBe('c1')
    expect(back.nodes[0]!.content?.content?.[0]?.content?.[0]).toEqual({ type: 'text', text: '参考答案' })
    const m = back.nodes[1]!
    expect(m.id).toBe('m1')
    expect(m.props).toEqual({ scope: 'all', fields: { answer: true, thinking: false, analysis: false, summary: false } })
    expect(m.children).toEqual([])
  })

  it('module drops derived answer_item and lifts custom note out', () => {
    const module: EditorNode = {
      id: 'm1', nodeType: 'question_details', content: null,
      props: { scope: 'all', fields: { answer: true, thinking: false, analysis: false, summary: false } },
      questionId: null, questionRevision: null, questionContent: null,
      sourceQuestionNodeId: null, anchorBeforeNodeId: null,
      children: [
        { id: 'note', nodeType: 'rich_text', content: { type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text: '注记' }] }] }, props: null, questionId: null, questionRevision: null, questionContent: null, sourceQuestionNodeId: null, anchorBeforeNodeId: 'ai1', schemaVersion: 2, children: [] },
        { id: 'ai1', nodeType: 'answer_item', content: null, props: { included: true, overrides: { answer: null, thinking: null, analysis: null, summary: null } }, questionId: null, questionRevision: null, questionContent: null, sourceQuestionNodeId: 'q1', anchorBeforeNodeId: null, children: [] },
      ],
    }
    const back = pmDocToEditorDocument(editorDocumentToPmDoc({ nodes: [module] }))
    // 注记上提为顶层 rich_text；answer_item 丢弃；模块 children 为空。
    expect(back.nodes.map((n) => n.nodeType)).toEqual(['rich_text', 'question_details'])
    expect(back.nodes[0]!.id).toBe('note')
    expect(back.nodes[0]!.content?.content?.[0]?.content?.[0]).toEqual({ type: 'text', text: '注记' })
    expect(back.nodes[1]!.children).toEqual([])
  })

  it('mixed document is stable across two round-trips', () => {
    const doc: EditorDocument = {
      nodes: [headingRow('h1', 1, 'Exam'), richTextRow('r1', 'intro'), questionRow('q1', 7), pageBreakRow('p1')],
    }
    const once = pmDocToEditorDocument(editorDocumentToPmDoc(doc))
    const twice = pmDocToEditorDocument(editorDocumentToPmDoc(once))
    expect(twice).toEqual(once)
  })

  it('legacy multi-block rich_text splits into independent rows, first keeps id', () => {
    const legacy: EditorDocument = {
      nodes: [
        {
          ...richTextRow('r1', 'first'),
          content: {
            type: 'doc',
            content: [
              { type: 'paragraph', content: [{ type: 'text', text: 'first' }] },
              { type: 'paragraph', content: [{ type: 'text', text: 'second' }] },
            ],
          },
        },
      ],
    }
    const back = pmDocToEditorDocument(editorDocumentToPmDoc(legacy))
    expect(back.nodes).toHaveLength(2)
    expect(back.nodes[0]!.id).toBe('r1')
    expect(back.nodes[1]!.id).not.toBe('r1')
    expect(back.nodes[1]!.content?.content?.[0]?.content?.[0]).toEqual({ type: 'text', text: 'second' })
  })
})
