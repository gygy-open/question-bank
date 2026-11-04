import type {
  StructDistribution,
  StructReviewQueuePage,
  StructSavePayload,
  StructSettings,
  StructSimilarItem,
  StructStats,
  StructTargetType,
  StructType,
  StructureView,
} from '@/types'

/**
 * 题干结构化 API(后端 /structure/*)。
 *
 * 只做请求封装,不缓存状态;错误由调用方用 apiErrorMessage 提示。
 */
export function useStructure() {
  const { $api } = useNuxtApp()

  // region 开关与权限

  /** 总开关;给定学科时附带「入库自动拆解」与当前用户在该学科的权限。 */
  const getSettings = (subjectId?: number | null) =>
    $api<StructSettings>('/structure/settings', { query: subjectId ? { subject_id: subjectId } : {} })

  /** 修改总开关(超级管理员)。 */
  const setEnabled = (enabled: boolean) =>
    $api<{ enabled: boolean }>('/structure/settings', { method: 'PUT', body: { enabled } })

  /** 修改学科的「入库自动拆解」(学科管理员)。 */
  const setAutoDecompose = (subjectId: number, autoDecompose: boolean) =>
    $api<{ auto_decompose: boolean }>(`/structure/subjects/${subjectId}/settings`, {
      method: 'PUT', body: { auto_decompose: autoDecompose },
    })

  // endregion

  // region 拆解

  /** 一道题(或一份材料)的结构化全貌。 */
  const getView = (targetType: StructTargetType, targetId: number) =>
    $api<StructureView>(`/structure/targets/${targetType}/${targetId}`)

  /** 排队拆解(单个或批量);返回入队 / 跳过的 id。 */
  const decompose = (targetIds: number[], targetType: StructTargetType = 'question') =>
    $api<{ queued: number[], skipped: number[], job_ids: number[] }>('/structure/decompose', {
      method: 'POST', body: { target_type: targetType, target_ids: targetIds },
    })

  /** 保存人工修改(新建人工快照,可同时采纳),返回最新全貌。 */
  const save = (payload: StructSavePayload) =>
    $api<StructureView>('/structure/save', { method: 'POST', body: payload })

  /** 采纳 / 驳回待审拆解(支持批量)。 */
  const review = (runIds: number[], action: 'accept' | 'reject') =>
    $api<{ updated: number[], skipped: number[] }>('/structure/review', {
      method: 'POST', body: { run_ids: runIds, action },
    })

  /** 为学科内尚未拆解的题排队(最低优先级)。 */
  const backfill = (subjectId: number, limit = 500) =>
    $api<{ queued: number }>('/structure/backfill', { method: 'POST', body: { subject_id: subjectId, limit } })

  /** 待审拆解列表(有错误的在前)。 */
  const reviewQueue = (subjectId: number, query: Record<string, unknown> = {}) =>
    $api<StructReviewQueuePage>('/structure/review-queue', { query: { subject_id: subjectId, ...query } })

  // endregion

  // region 同结构题与统计

  const similar = (questionId: number, limit = 10) =>
    $api<{ items: StructSimilarItem[] }>(`/structure/questions/${questionId}/similar`, { query: { limit } })

  const stats = (subjectId: number) =>
    $api<StructStats>('/structure/stats', { query: { subject_id: subjectId } })

  const distribution = (questionIds: number[]) =>
    $api<StructDistribution>('/structure/distribution', { method: 'POST', body: { question_ids: questionIds } })

  // endregion

  // region 元素类型树

  const listTypes = (subjectId: number) =>
    $api<{ items: StructType[] }>('/structure/types', { query: { subject_id: subjectId } })

  const createType = (payload: Partial<StructType> & { subject_id: number, name: string }) =>
    $api<StructType>('/structure/types', { method: 'POST', body: payload })

  /** 部分修改;body 中出现 parent_id(含 null)即表示移动。 */
  const updateType = (typeId: number, changes: Partial<StructType>) =>
    $api<StructType>(`/structure/types/${typeId}`, { method: 'PATCH', body: changes })

  const deleteType = (typeId: number) =>
    $api<{ ok: boolean }>(`/structure/types/${typeId}`, { method: 'DELETE' })

  /** 把 typeId 合并进 targetId(引用与子节点一并迁移)。 */
  const mergeType = (typeId: number, targetId: number) =>
    $api<StructType>(`/structure/types/${typeId}/merge`, { method: 'POST', body: { target_id: targetId } })

  const exportTypes = (subjectId: number) =>
    $api<Array<Record<string, unknown>>>('/structure/types/export', { query: { subject_id: subjectId } })

  const importTypes = (subjectId: number, items: Array<Record<string, unknown>>) =>
    $api<{ created: number, updated: number }>('/structure/types/import', {
      method: 'POST', body: { subject_id: subjectId, items },
    })

  // endregion

  return {
    getSettings,
    setEnabled,
    setAutoDecompose,
    getView,
    decompose,
    save,
    review,
    backfill,
    reviewQueue,
    similar,
    stats,
    distribution,
    listTypes,
    createType,
    updateType,
    deleteType,
    mergeType,
    exportTypes,
    importTypes,
  }
}

/**
 * 结构化总开关的全局状态(侧边栏、题库列表、首页等共用,只请求一次)。
 *
 * enabled 在拿到结果前为 null;关闭时各处隐藏结构化入口。修改开关后调用 refresh()。
 */
export function useStructureEnabled() {
  const enabled = useState<boolean | null>('structure-enabled', () => null)
  const { getSettings } = useStructure()

  const refresh = async (): Promise<boolean | null> => {
    try {
      enabled.value = (await getSettings()).enabled
    } catch {
      // 请求失败(例如未登录)时保持未知,不阻塞页面。
      enabled.value = null
    }
    return enabled.value
  }

  return { enabled, refresh }
}
