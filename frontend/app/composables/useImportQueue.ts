import { computed, ref } from 'vue'

export type ImportStatus =
  | 'pending'
  | 'processing'
  | 'review_ready'
  | 'paused'
  | 'completed'
  | 'failed'
  | 'cancelled'

export type ImportPauseReason = 'quota' | 'auth' | 'model' | 'unavailable'
export type ImportMethod = 'auto' | 'ai' | 'structured'
export type ImportMode = 'extract' | 'solve'

export interface ImportProgress {
  stage?: 'parsing' | 'extracting' | 'matching' | 'ready' | 'done' | 'failed'
  method?: 'ai' | 'structured'
  count?: number
  error_code?: string
}

export interface ImportTaskItem {
  id: number
  original_filename: string
  description: string | null
  source: string | null
  file_type: string
  status: ImportStatus
  method: ImportMethod | null
  mode: ImportMode | null
  auto_commit: boolean
  subject_id: number | null
  progress: ImportProgress
  paused_reason: ImportPauseReason | null
  error_message: string | null
  result_summary: string | null
  has_result: boolean
  queue_ahead: number | null
  owner_id: number | null
  owner_name: string | null
  created_at: string
  updated_at: string | null
}

export interface ImportSummary {
  counts: Partial<Record<ImportStatus, number>>
  paused_reasons: Partial<Record<ImportPauseReason, number>>
}

export const ACTIVE_IMPORT_STATUSES: ImportStatus[] = ['pending', 'processing']

const PAGE_STEP = 50

// 模块级共享:侧边栏角标、列表与详情页看到的是同一份数据。
const tasks = ref<ImportTaskItem[]>([])
const total = ref(0)
const summary = ref<ImportSummary | null>(null)
// null:只看自己的;'all':管理员查看全部;数字:管理员查看某个用户的。
const ownerFilter = ref<number | 'all' | null>(null)
const pageSize = ref(PAGE_STEP)
const loaded = ref(false)

export function isActiveImport(task: Pick<ImportTaskItem, 'status'>): boolean {
  return ACTIVE_IMPORT_STATUSES.includes(task.status)
}

export function useImportQueue() {
  const { $api } = useNuxtApp()
  const { user } = useAuth()

  const refreshSummary = async () => {
    try {
      summary.value = await $api<ImportSummary>('/imports/summary')
    } catch {
      // 角标只是提示,失败时保留上次的值
    }
  }

  const refresh = async () => {
    const query: Record<string, unknown> = { size: pageSize.value }
    if (ownerFilter.value === null) query.user_id = user.value?.id
    else if (ownerFilter.value !== 'all') query.user_id = ownerFilter.value
    try {
      const data = await $api<{ items: ImportTaskItem[]; total: number }>('/imports', { query })
      tasks.value = data.items
      total.value = data.total
      loaded.value = true
    } catch (e) {
      console.error('Failed to load imports', e)
    }
    await refreshSummary()
  }

  const loadMore = async () => {
    pageSize.value += PAGE_STEP
    await refresh()
  }

  /** 详情页拿到的新状态同步进列表,不必等下一轮轮询。 */
  const upsert = (task: ImportTaskItem) => {
    const index = tasks.value.findIndex((item) => item.id === task.id)
    if (index >= 0) tasks.value.splice(index, 1, task)
    else tasks.value.unshift(task)
  }

  const remove = (id: number) => {
    tasks.value = tasks.value.filter((item) => item.id !== id)
  }

  return {
    tasks,
    total,
    summary,
    ownerFilter,
    loaded,
    hasMore: computed(() => tasks.value.length < total.value),
    hasActive: computed(() => tasks.value.some(isActiveImport)),
    reviewCount: computed(() => summary.value?.counts.review_ready ?? 0),
    refresh,
    refreshSummary,
    loadMore,
    upsert,
    remove,
  }
}
