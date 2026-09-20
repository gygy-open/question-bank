import { describe, expect, it } from 'vitest'

import {
  buildSubmitOutline,
  hasPaperStructure,
  insertQuestionRefAfter,
  outlineFromDrafts,
  pruneOutline,
  reorderQuestionRefs,
  type PaperOutlineItem,
} from '@/lib/paperOutline'
import type { ImportDraft } from '@/lib/questionModel'

function draft(tempId: string, extra: Partial<ImportDraft> = {}): ImportDraft {
  return {
    uid: `uid-${tempId}`,
    selected: true,
    warnings: [],
    temp_id: tempId,
    parent_temp_id: null,
    source_number: null,
    content: null,
    q_type: 'free_response',
    status: 'draft',
    difficulty: 3,
    visibility: 'public',
    options: [],
    answer: null,
    thinking: null,
    analysis: null,
    summary: null,
    source: '',
    knowledge_point_ids: [],
    tag_ids: [],
    parent_id: null,
    ...extra,
  } as ImportDraft
}

const paper: PaperOutlineItem[] = [
  { kind: 'heading', text: '一、选择题', level: 2 },
  { kind: 'question_ref', temp_id: 'a', number: '1' },
  { kind: 'question_ref', temp_id: 'b', number: '2' },
  { kind: 'heading', text: '二、解答题', level: 2 },
  { kind: 'question_ref', temp_id: 'c', number: '3' },
]

describe('hasPaperStructure', () => {
  it('只有题目引用时视为没有版面结构', () => {
    expect(hasPaperStructure({ outline: [{ kind: 'question_ref', temp_id: 'a' }] })).toBe(false)
  })

  it('含标题或说明时视为有版面结构', () => {
    expect(hasPaperStructure({ outline: paper })).toBe(true)
  })

  it('缺省与空结构都视为没有', () => {
    expect(hasPaperStructure(null)).toBe(false)
    expect(hasPaperStructure({ outline: [] })).toBe(false)
  })
})

describe('pruneOutline', () => {
  it('删掉的题目不留下悬空引用，标题保留', () => {
    const result = pruneOutline(paper, ['a', 'c'])

    expect(result.map((i) => i.kind)).toEqual([
      'heading',
      'question_ref',
      'heading',
      'question_ref',
    ])
    expect(result.filter((i) => i.kind === 'question_ref').map((i) => i.temp_id)).toEqual(['a', 'c'])
  })

  it('没有 temp_id 的题目引用一律丢弃', () => {
    expect(pruneOutline([{ kind: 'question_ref' }], [])).toEqual([])
  })
})

describe('insertQuestionRefAfter', () => {
  it('复制题目时在原题之后补一个引用', () => {
    const result = insertQuestionRefAfter(paper, 'a', 'a-copy')

    expect(result.filter((i) => i.kind === 'question_ref').map((i) => i.temp_id)).toEqual([
      'a',
      'a-copy',
      'b',
      'c',
    ])
  })

  it('找不到锚点时追加到末尾', () => {
    const result = insertQuestionRefAfter(paper, 'missing', 'x')

    expect(result[result.length - 1]).toEqual({ kind: 'question_ref', temp_id: 'x', number: null })
  })
})

describe('reorderQuestionRefs', () => {
  it('按新顺序填回题目引用，标题位置不动', () => {
    const result = reorderQuestionRefs(paper, ['c', 'b', 'a'])

    expect(result.map((i) => i.kind)).toEqual([
      'heading',
      'question_ref',
      'question_ref',
      'heading',
      'question_ref',
    ])
    expect(result.filter((i) => i.kind === 'question_ref').map((i) => i.temp_id)).toEqual([
      'c',
      'b',
      'a',
    ])
  })

  it('保留原引用上的题号信息', () => {
    const result = reorderQuestionRefs(paper, ['c', 'a', 'b'])
    const first = result.find((i) => i.kind === 'question_ref')

    expect(first).toMatchObject({ temp_id: 'c', number: '3' })
  })
})

describe('outlineFromDrafts', () => {
  it('退化为按顺序的题目引用，并带上原题号', () => {
    const result = outlineFromDrafts([
      draft('a', { source_number: '5' }),
      draft('b'),
    ])

    expect(result).toEqual([
      { kind: 'question_ref', temp_id: 'a', number: '5' },
      { kind: 'question_ref', temp_id: 'b', number: null },
    ])
  })

  it('子题不进 outline（由母题承载）', () => {
    const result = outlineFromDrafts([draft('p'), draft('c', { parent_temp_id: 'p' })])

    expect(result.map((i) => i.temp_id)).toEqual(['p'])
  })
})

describe('buildSubmitOutline', () => {
  it('有版面结构时裁剪并按当前顺序重排', () => {
    const result = buildSubmitOutline({ outline: paper }, [draft('c'), draft('a')])

    expect(result.map((i) => i.kind)).toEqual(['heading', 'question_ref', 'heading', 'question_ref'])
    expect(result.filter((i) => i.kind === 'question_ref').map((i) => i.temp_id)).toEqual(['c', 'a'])
  })

  it('没有版面结构时按题目顺序生成', () => {
    const result = buildSubmitOutline(null, [draft('a'), draft('b')])

    expect(result.map((i) => i.temp_id)).toEqual(['a', 'b'])
  })

  it('题组成员不会替换独立题引用', () => {
    const result = buildSubmitOutline({
      outline: [
        { kind: 'question_group_ref', temp_id: 'group' },
        { kind: 'question_ref', temp_id: 'solo', number: '3' },
      ],
    }, [draft('member'), draft('solo')])

    expect(result).toEqual([
      { kind: 'question_group_ref', temp_id: 'group' },
      { kind: 'question_ref', temp_id: 'solo', number: '3' },
    ])
  })
})
