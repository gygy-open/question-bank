import type { ImportDraft } from '@/lib/questionModel'
import type { PaperExtraction, PaperOutlineItem } from '@/lib/paperOutline'
import type { RichDoc } from '@/types'

export interface ImportStimulus {
  temp_id: string
  content: RichDoc | null
  metadata?: Record<string, unknown>
  status?: string
  visibility?: string
  source?: string | null
}

export interface ImportQuestionGroup {
  temp_id: string
  stimulus_temp_id: string
  question_temp_ids: string[]
  metadata?: Record<string, unknown>
  status?: string
  visibility?: string
  source?: string | null
}

export type ImportReviewEntry =
  | { kind: 'question'; question: ImportDraft; index: number }
  | {
      kind: 'question_group'
      group: ImportQuestionGroup
      stimulus: ImportStimulus | null
      members: Array<{ question: ImportDraft; index: number }>
    }

export interface ImportStructurePayload {
  questions: Record<string, unknown>[]
  outline: PaperOutlineItem[]
  stimuli: ImportStimulus[]
  question_groups: ImportQuestionGroup[]
}

function duplicateValues(values: string[]): string[] {
  const seen = new Set<string>()
  const duplicates = new Set<string>()
  for (const value of values) {
    if (seen.has(value)) duplicates.add(value)
    seen.add(value)
  }
  return [...duplicates]
}

export function validateImportStructure(
  questions: ImportDraft[],
  stimuli: ImportStimulus[],
  groups: ImportQuestionGroup[],
  paper?: PaperExtraction | null,
): string[] {
  const errors: string[] = []
  const questionIds = questions.map((question) => question.temp_id).filter((id): id is string => !!id)
  const stimulusIds = stimuli.map((stimulus) => stimulus.temp_id)
  const groupIds = groups.map((group) => group.temp_id)

  for (const id of duplicateValues(questionIds)) errors.push(`题目临时引用重复：${id}`)
  for (const id of duplicateValues(stimulusIds)) errors.push(`题目材料临时引用重复：${id}`)
  for (const id of duplicateValues(groupIds)) errors.push(`题组临时引用重复：${id}`)

  const questionIdSet = new Set(questionIds)
  const stimulusIdSet = new Set(stimulusIds)
  const groupIdSet = new Set(groupIds)
  for (const group of groups) {
    if (!stimulusIdSet.has(group.stimulus_temp_id)) {
      errors.push(`题组 ${group.temp_id} 引用了不存在的题目材料：${group.stimulus_temp_id}`)
    }
    if (group.question_temp_ids.length === 0) errors.push(`题组 ${group.temp_id} 没有小题`)
    for (const id of duplicateValues(group.question_temp_ids)) {
      errors.push(`题组 ${group.temp_id} 重复引用小题：${id}`)
    }
    for (const id of group.question_temp_ids) {
      if (!questionIdSet.has(id)) errors.push(`题组 ${group.temp_id} 引用了不存在的小题：${id}`)
    }
  }

  for (const item of paper?.outline ?? []) {
    if (item.kind === 'question_ref' && item.temp_id && !questionIdSet.has(item.temp_id)) {
      errors.push(`试卷结构引用了不存在的题目：${item.temp_id}`)
    }
    if (item.kind === 'question_group_ref' && item.temp_id && !groupIdSet.has(item.temp_id)) {
      errors.push(`试卷结构引用了不存在的题组：${item.temp_id}`)
    }
  }
  return errors
}

export function buildImportReviewEntries(
  questions: ImportDraft[],
  stimuli: ImportStimulus[],
  groups: ImportQuestionGroup[],
  paper?: PaperExtraction | null,
): ImportReviewEntry[] {
  const questionById = new Map(questions.filter((q) => q.temp_id).map((q, index) => [q.temp_id!, { question: q, index }]))
  const stimulusById = new Map(stimuli.map((stimulus) => [stimulus.temp_id, stimulus]))
  const groupById = new Map(groups.map((group) => [group.temp_id, group]))
  const memberIds = new Set(groups.flatMap((group) => group.question_temp_ids))
  const renderedQuestions = new Set<string>()
  const renderedGroups = new Set<string>()
  const entries: ImportReviewEntry[] = []

  const appendQuestion = (id: string) => {
    if (renderedQuestions.has(id) || memberIds.has(id)) return
    const found = questionById.get(id)
    if (!found) return
    renderedQuestions.add(id)
    entries.push({ kind: 'question', ...found })
  }
  const appendGroup = (id: string) => {
    if (renderedGroups.has(id)) return
    const group = groupById.get(id)
    if (!group) return
    renderedGroups.add(id)
    const members = group.question_temp_ids
      .map((questionId) => questionById.get(questionId))
      .filter((member): member is { question: ImportDraft; index: number } => !!member)
    entries.push({
      kind: 'question_group',
      group,
      stimulus: stimulusById.get(group.stimulus_temp_id) ?? null,
      members,
    })
  }

  for (const item of paper?.outline ?? []) {
    if (item.kind === 'question_group_ref' && item.temp_id) appendGroup(item.temp_id)
    if (item.kind === 'question_ref' && item.temp_id) appendQuestion(item.temp_id)
  }

  for (const question of questions) {
    if (!question.temp_id) continue
    for (const group of groups) {
      if (group.question_temp_ids[0] === question.temp_id) appendGroup(group.temp_id)
    }
    appendQuestion(question.temp_id)
  }
  for (const group of groups) appendGroup(group.temp_id)
  return entries
}

export function buildImportStructurePayload(
  payloadQuestions: Record<string, unknown>[],
  selectedQuestions: ImportDraft[],
  stimuli: ImportStimulus[],
  groups: ImportQuestionGroup[],
  paper?: PaperExtraction | null,
): ImportStructurePayload {
  const selectedIds = new Set(selectedQuestions.map((question) => question.temp_id).filter(Boolean))
  const groupIds = new Set(groups.map((group) => group.temp_id))
  const outline = paper?.outline?.length
    ? paper.outline.filter((item) => {
        if (item.kind === 'question_ref') return !!item.temp_id && selectedIds.has(item.temp_id)
        if (item.kind === 'question_group_ref') return !!item.temp_id && groupIds.has(item.temp_id)
        return true
      })
    : buildImportReviewEntries(selectedQuestions, stimuli, groups)
        .filter((entry) => entry.kind === 'question_group' || !entry.question.parent_temp_id)
        .map((entry) => ({
          kind: entry.kind === 'question' ? 'question_ref' as const : 'question_group_ref' as const,
          temp_id: entry.kind === 'question' ? entry.question.temp_id! : entry.group.temp_id,
          number: entry.kind === 'question' ? entry.question.source_number : null,
        }))

  return { questions: payloadQuestions, outline, stimuli, question_groups: groups }
}