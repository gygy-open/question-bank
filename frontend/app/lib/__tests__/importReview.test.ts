import { describe, expect, it } from 'vitest'

import {
  buildImportReviewEntries,
  buildImportStructurePayload,
  validateImportStructure,
  type ImportQuestionGroup,
  type ImportStimulus,
} from '@/lib/importReview'
import type { ImportDraft } from '@/lib/questionModel'

const draft = (tempId: string, selected = true) => ({
  uid: `uid-${tempId}`,
  temp_id: tempId,
  selected,
  source_number: tempId,
} as ImportDraft)

const stimuli: ImportStimulus[] = [
  { temp_id: 's1', content: { type: 'doc', content: [] } },
]
const groups: ImportQuestionGroup[] = [
  { temp_id: 'g1', stimulus_temp_id: 's1', question_temp_ids: ['q2', 'q1'] },
]

describe('buildImportReviewEntries', () => {
  it('按题组引用展示材料和原始小题顺序，独立题保持独立', () => {
    const questions = [draft('q1'), draft('solo'), draft('q2')]
    const entries = buildImportReviewEntries(questions, stimuli, groups, {
      outline: [
        { kind: 'question_group_ref', temp_id: 'g1' },
        { kind: 'question_ref', temp_id: 'solo' },
      ],
    })

    expect(entries.map((entry) => entry.kind)).toEqual(['question_group', 'question'])
    expect(entries[0]?.kind === 'question_group' && entries[0].members.map((member) => member.question.temp_id)).toEqual(['q2', 'q1'])
  })

  it('多个题组可复用同一题目材料', () => {
    const entries = buildImportReviewEntries(
      [draft('q1'), draft('q2')],
      stimuli,
      [...groups, { temp_id: 'g2', stimulus_temp_id: 's1', question_temp_ids: ['q2'] }],
    )

    expect(entries.filter((entry) => entry.kind === 'question_group')).toHaveLength(2)
  })
})

describe('validateImportStructure', () => {
  it('报告悬空材料、悬空小题、重复成员和悬空 outline 引用', () => {
    const errors = validateImportStructure(
      [draft('q1')],
      stimuli,
      [{ temp_id: 'g1', stimulus_temp_id: 'missing', question_temp_ids: ['q1', 'q1', 'q2'] }],
      { outline: [{ kind: 'question_group_ref', temp_id: 'missing-group' }] },
    )

    expect(errors).toEqual(expect.arrayContaining([
      expect.stringContaining('不存在的题目材料'),
      expect.stringContaining('重复引用小题'),
      expect.stringContaining('不存在的小题'),
      expect.stringContaining('不存在的题组'),
    ]))
  })
})

describe('buildImportStructurePayload', () => {
  it('只裁掉未选独立题引用，不改变题组引用、成员或顺序', () => {
    const questions = [draft('q1'), draft('q2'), draft('solo', false)]
    const outline = [
      { kind: 'question_group_ref' as const, temp_id: 'g1' },
      { kind: 'question_ref' as const, temp_id: 'solo' },
    ]
    const result = buildImportStructurePayload(
      [{ temp_id: 'q1' }, { temp_id: 'q2' }],
      questions.filter((question) => question.selected),
      stimuli,
      groups,
      { outline },
    )

    expect(result.outline).toEqual([outline[0]])
    expect(result.question_groups).toEqual(groups)
    expect(result.stimuli).toEqual(stimuli)
  })

  it('无 outline 时不为旧派生子题生成独立引用', () => {
    const parent = draft('parent')
    const child = { ...draft('child'), parent_temp_id: 'parent' }
    const result = buildImportStructurePayload(
      [{ temp_id: 'parent' }, { temp_id: 'child' }],
      [parent, child],
      [],
      [],
    )

    expect(result.outline).toEqual([
      { kind: 'question_ref', temp_id: 'parent', number: 'parent' },
    ])
  })
})