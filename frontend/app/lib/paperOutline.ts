// 整卷导入的版面结构（outline）维护 —— 纯函数，不依赖 Nuxt 运行时。
// 与后端 app/services/importing/contracts.py 的 outline 契约对齐。
//
// 审核页可以删题、复制题、调整顺序，outline 必须随之保持一致：
// 删掉的题不能留下悬空引用，复制出来的题要在原题后面补一个引用。

import type { ImportDraft } from '@/lib/questionModel'

export type PaperOutlineKind =
  | 'heading'
  | 'rich_text'
  | 'question_ref'
  | 'page_break'
  | 'answer_space'
  | 'details_module'
  | 'degraded'

export interface PaperOutlineItem {
  kind: PaperOutlineKind
  text?: string
  level?: number
  markdown?: string
  reason?: string
  temp_id?: string
  number?: string | null
  score?: number | null
  lines?: number
  style?: string
  scope?: string
  fields?: Record<string, boolean>
}

export interface PaperExtraction {
  suggested_title?: string | null
  outline?: PaperOutlineItem[]
}

/** 抽取阶段是否识别出了题目之外的版面结构（标题/说明等）。 */
export function hasPaperStructure(paper: PaperExtraction | null | undefined): boolean {
  return !!paper?.outline?.some((item) => item.kind !== 'question_ref')
}

/**
 * 丢弃引用了不存在题目的 question_ref。
 * 审核页删题后调用，避免把悬空引用发给后端。
 */
export function pruneOutline(
  outline: PaperOutlineItem[],
  liveTempIds: Iterable<string>,
): PaperOutlineItem[] {
  const alive = new Set(liveTempIds)
  return outline.filter(
    (item) => item.kind !== 'question_ref' || (!!item.temp_id && alive.has(item.temp_id)),
  )
}

/** 在指定题目的引用之后插入一个新引用（复制题目时用）。 */
export function insertQuestionRefAfter(
  outline: PaperOutlineItem[],
  afterTempId: string,
  newTempId: string,
): PaperOutlineItem[] {
  const index = outline.findIndex(
    (item) => item.kind === 'question_ref' && item.temp_id === afterTempId,
  )
  const ref: PaperOutlineItem = { kind: 'question_ref', temp_id: newTempId, number: null }
  if (index === -1) return [...outline, ref]
  return [...outline.slice(0, index + 1), ref, ...outline.slice(index + 1)]
}

/**
 * 按审核列表的当前顺序重排 outline 里的题目引用。
 * 非题目项（标题、说明）保持原有相对位置，题目引用按列表顺序依次填回。
 */
export function reorderQuestionRefs(
  outline: PaperOutlineItem[],
  orderedTempIds: string[],
): PaperOutlineItem[] {
  const byTempId = new Map(
    outline
      .filter((item) => item.kind === 'question_ref' && item.temp_id)
      .map((item) => [item.temp_id as string, item]),
  )
  const queue = orderedTempIds
    .map((id) => byTempId.get(id) ?? { kind: 'question_ref' as const, temp_id: id, number: null })
  let cursor = 0
  return outline.map((item) =>
    item.kind === 'question_ref' ? (queue[cursor++] ?? item) : item,
  )
}

/** 抽取未识别版面结构时，退化为按选中顺序排列的题目引用。 */
export function outlineFromDrafts(drafts: ImportDraft[]): PaperOutlineItem[] {
  return drafts
    .filter((d) => !!d.temp_id && !d.parent_temp_id)
    .map((d) => ({
      kind: 'question_ref' as const,
      temp_id: d.temp_id as string,
      number: d.source_number ?? null,
    }))
}

/**
 * 由当前选中的题目推导出要提交的 outline。
 * 有真实版面结构时在其上裁剪，否则退化为题目序列。
 */
export function buildSubmitOutline(
  paper: PaperExtraction | null | undefined,
  selected: ImportDraft[],
): PaperOutlineItem[] {
  const tempIds = selected.map((d) => d.temp_id).filter((id): id is string => !!id)
  if (!hasPaperStructure(paper)) return outlineFromDrafts(selected)
  const pruned = pruneOutline(paper?.outline ?? [], tempIds)
  return reorderQuestionRefs(pruned, tempIds)
}
