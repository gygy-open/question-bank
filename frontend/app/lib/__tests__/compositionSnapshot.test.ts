import { describe, it, expect } from 'vitest'
import type {
  CompositionSnapshotV1,
  QuestionSnapshot,
  SnapshotAnswerSummaryBlock,
  SnapshotBlock,
} from '@/types/composition'
import { snapshotQuestionMap, resolveSummaryQuestions } from '@/lib/compositionSnapshot'

function richDoc(text: string) {
  return { type: 'doc' as const, content: [{ type: 'paragraph', content: [{ type: 'text', text }] }] }
}

function qsnap(id: number, stem = `Q${id}`): QuestionSnapshot {
  return {
    id,
    content_revision: 1,
    content_schema_version: 2,
    q_type: 'single_choice',
    content: richDoc(stem),
    options: [{ id: 'opt_a', label: 'A', content: richDoc('2') }],
    answer: { kind: 'single_choice', correct: 'opt_a' },
    thinking: null,
    analysis: richDoc(`解析${id}`),
    summary: null,
    difficulty: 3,
    source: 'seed',
  }
}

function snapshot(blocks: SnapshotBlock[]): CompositionSnapshotV1 {
  return {
    schema_version: 1,
    composition_id: 1,
    source_revision: 2,
    title: '稿件',
    subject_id: 1,
    finalized_at: '2026-01-01T00:00:00Z',
    blocks,
  }
}

function questionBlock(q: QuestionSnapshot): SnapshotBlock {
  return { block_type: 'question', question_id: q.id, question_revision: q.content_revision, question: q }
}

function summaryBlock(mode: 'all' | 'before', ids: number[]): SnapshotAnswerSummaryBlock {
  return { block_type: 'answer_summary', props: { mode }, resolved_question_ids: ids }
}

describe('snapshotQuestionMap', () => {
  it('按 question_id 收录内嵌题目，重复保留首个', () => {
    const q1 = qsnap(1, '首个')
    const q1b = qsnap(1, '重复')
    const q2 = qsnap(2)
    const map = snapshotQuestionMap(
      snapshot([questionBlock(q1), questionBlock(q2), questionBlock(q1b)]),
    )
    expect([...map.keys()]).toEqual([1, 2])
    expect(map.get(1)!.content).toEqual(richDoc('首个'))
  })

  it('跳过内容缺失（question=null）的 question block', () => {
    const map = snapshotQuestionMap(
      snapshot([
        { block_type: 'question', question_id: 9, question_revision: 1, question: null },
        questionBlock(qsnap(2)),
      ]),
    )
    expect([...map.keys()]).toEqual([2])
  })
})

describe('resolveSummaryQuestions', () => {
  const q1 = qsnap(1)
  const q2 = qsnap(2)
  const q3 = qsnap(3)
  // 顺序对应后端去重保序：q1 出现两次，被后端去重为 [q1, q2, q3]。
  const snap = snapshot([
    questionBlock(q1),
    summaryBlock('before', [1]),
    questionBlock(q2),
    questionBlock(q1),
    questionBlock(q3),
    summaryBlock('all', [1, 2, 3]),
    summaryBlock('before', [1, 2, 3]),
  ])

  it('mode=before：按 resolved ids 顺序解析该块之前的题目', () => {
    const before = snap.blocks[1] as SnapshotAnswerSummaryBlock
    expect(resolveSummaryQuestions(snap, before).map((q) => q.id)).toEqual([1])
  })

  it('mode=all：按 resolved ids 顺序解析全篇题目', () => {
    const all = snap.blocks[5] as SnapshotAnswerSummaryBlock
    expect(resolveSummaryQuestions(snap, all).map((q) => q.id)).toEqual([1, 2, 3])
  })

  it('保持 resolved ids 顺序而非快照出现顺序', () => {
    const reordered = summaryBlock('all', [3, 1, 2])
    expect(resolveSummaryQuestions(snap, reordered).map((q) => q.id)).toEqual([3, 1, 2])
  })

  it('缺失内容的 id 被跳过', () => {
    const withMissing = summaryBlock('all', [1, 99, 2])
    expect(resolveSummaryQuestions(snap, withMissing).map((q) => q.id)).toEqual([1, 2])
  })

  it('空 resolved ids 返回空数组', () => {
    expect(resolveSummaryQuestions(snap, summaryBlock('all', []))).toEqual([])
  })
})
