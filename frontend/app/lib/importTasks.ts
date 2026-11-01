import type { ImportTaskItem } from '@/composables/useImportQueue'

export type ImportGroup = 'review' | 'active' | 'paused' | 'failed' | 'history'

export const IMPORT_GROUP_ORDER: ImportGroup[] = ['review', 'active', 'paused', 'failed', 'history']

/** i18n 键与参数;由调用方在模板/computed 中翻译,避免在模块作用域缓存译文。 */
export interface I18nMessage {
  key: string
  params?: Record<string, unknown>
}

export const FAILURE_CODES = ['no_questions', 'source_unavailable', 'parse_failed', 'ai_document', 'ai_unknown'] as const

export function groupOf(task: Pick<ImportTaskItem, 'status'>): ImportGroup {
  switch (task.status) {
    case 'review_ready': return 'review'
    case 'pending':
    case 'processing': return 'active'
    case 'paused': return 'paused'
    case 'failed': return 'failed'
    default: return 'history'
  }
}

export function groupTasks(tasks: ImportTaskItem[]): { group: ImportGroup; tasks: ImportTaskItem[] }[] {
  const buckets = new Map<ImportGroup, ImportTaskItem[]>()
  for (const task of tasks) {
    const group = groupOf(task)
    if (!buckets.has(group)) buckets.set(group, [])
    buckets.get(group)!.push(task)
  }
  return IMPORT_GROUP_ORDER
    .filter((group) => buckets.has(group))
    .map((group) => ({ group, tasks: buckets.get(group)! }))
}

export function createdCount(task: Pick<ImportTaskItem, 'result_summary'>): number {
  if (!task.result_summary) return 0
  try {
    const summary = JSON.parse(task.result_summary)
    return summary.count ?? summary.created_question_ids?.length ?? 0
  } catch {
    return 0
  }
}

export function failureMessage(task: Pick<ImportTaskItem, 'progress'>): I18nMessage {
  const code = task.progress?.error_code
  if (code === 'no_questions' && task.progress?.method === 'structured') {
    return { key: 'imports.errors.noQuestionsStructured', params: { tag: '【题目】' } }
  }
  if (code && (FAILURE_CODES as readonly string[]).includes(code)) {
    return { key: `imports.errors.${code}` }
  }
  return { key: 'imports.errors.generic' }
}

/** 列表里文件名下方的一行状态说明。 */
export function statusLine(task: ImportTaskItem): I18nMessage {
  switch (task.status) {
    case 'pending':
      return task.queue_ahead
        ? { key: 'imports.line.queuedAhead', params: { count: task.queue_ahead } }
        : { key: 'imports.line.queued' }
    case 'processing':
      return { key: `imports.stages.${task.progress?.stage === 'matching' || task.progress?.stage === 'extracting' ? task.progress.stage : 'parsing'}` }
    case 'review_ready':
      return { key: 'imports.line.questions', params: { count: task.progress?.count ?? 0 } }
    case 'paused':
      return { key: `imports.line.paused.${task.paused_reason ?? 'unavailable'}` }
    case 'failed':
      return failureMessage(task)
    case 'completed':
      return { key: 'imports.line.saved', params: { count: createdCount(task) } }
    default:
      return { key: 'imports.statuses.cancelled' }
  }
}
