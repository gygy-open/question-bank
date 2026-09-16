<script setup lang="ts">
// 评测投放场次详情：概览 / 成绩册（追加式录分）/ 题目统计。
// 逐行草稿，只提交相较已加载行发生变化的题目；乐观锁冲突(409)统一 toast 后刷新当前页。
// 资源在当前学科强上下文下。
import { ref, computed, watch, onActivated } from 'vue'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  ArrowLeft,
  Loader2,
  Play,
  Lock,
  Save,
  AlertTriangle,
  CheckCircle2,
  Download,
  Upload,
} from '@lucide/vue'
import { toast } from 'vue-sonner'
import { useAssessments, AssessmentConflictError } from '~/composables/useAssessments'
import { useSubjectContext } from '~/composables/useSubjectContext'
import { Capability, usePermissions } from '~/composables/usePermissions'
import type {
  GradingStatus,
  Gradebook,
  GradebookRow,
  ItemStatistics,
  ScoreImportPreview,
  SessionDetail,
} from '~/types/assessment'

const PAGE_SIZE = 20

const route = useRoute()
const router = useRouter()
const api = useAssessments()
const { currentSubjectId } = useSubjectContext()
const { can } = usePermissions()

const sessionId = computed(() => Number(route.params.id))
const canEditScores = computed(() => can(Capability.EDIT_SCORE, currentSubjectId.value))

const session = ref<SessionDetail | null>(null)
const loading = ref(false)
const error = ref(false)
const transitioning = ref(false)
const finalizeConfirmOpen = ref(false)
const activeTab = ref('overview')

const GRADING_META: Record<GradingStatus, { label: string; variant: 'secondary' | 'default' | 'outline' }> = {
  not_started: { label: '未开始', variant: 'outline' },
  in_progress: { label: '评分中', variant: 'default' },
  finalized: { label: '已定稿', variant: 'secondary' },
}
const DELIVERY_META: Record<string, { label: string; variant: 'secondary' | 'default' | 'outline' }> = {
  draft: { label: '草稿', variant: 'outline' },
  open: { label: '开放', variant: 'default' },
  closed: { label: '关闭', variant: 'secondary' },
}
const ATTENDANCE_META: Record<string, { label: string; variant: 'secondary' | 'default' | 'outline' | 'destructive' }> = {
  present: { label: '出席', variant: 'default' },
  absent: { label: '缺席', variant: 'destructive' },
  excused: { label: '请假', variant: 'secondary' },
}

function gradingMeta(status: string) {
  return GRADING_META[status as GradingStatus] ?? { label: status, variant: 'outline' as const }
}
function deliveryMeta(status: string) {
  return DELIVERY_META[status] ?? { label: status, variant: 'outline' as const }
}
function attendanceMeta(status: string) {
  return ATTENDANCE_META[status] ?? { label: status, variant: 'secondary' as const }
}

const gradingStatus = computed<string | null>(() => session.value?.grading_status ?? null)
const isNotStarted = computed(() => gradingStatus.value === 'not_started')
const isInProgress = computed(() => gradingStatus.value === 'in_progress')
const isFinalized = computed(() => gradingStatus.value === 'finalized')
const canEditGrades = computed(() => canEditScores.value && isInProgress.value)

function formatTime(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

// -------------------------------------------------------------- 加载 session //
async function loadSession() {
  if (!currentSubjectId.value || !Number.isFinite(sessionId.value)) return
  loading.value = true
  error.value = false
  try {
    session.value = await api.getSession(currentSubjectId.value, sessionId.value)
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}

onActivated(loadSession)
watch([currentSubjectId, sessionId], () => {
  session.value = null
  gradebook.value = null
  statistics.value = null
  gradebookLoaded.value = false
  statisticsLoaded.value = false
  page.value = 1
  loadSession()
})

// -------------------------------------------------------------- 状态流转 //
async function startGrading() {
  if (!currentSubjectId.value || transitioning.value) return
  transitioning.value = true
  try {
    session.value = await api.startGrading(currentSubjectId.value, sessionId.value)
    toast.success('已开始评分')
    await refreshData()
  } catch (e) {
    if (e instanceof AssessmentConflictError) {
      toast.error(`操作冲突：${e.detail || '状态已变更'}`)
      await loadSession()
    } else {
      toast.error((e as Error)?.message || '操作失败')
    }
  } finally {
    transitioning.value = false
  }
}

async function confirmFinalize() {
  if (!currentSubjectId.value || transitioning.value) return
  transitioning.value = true
  try {
    session.value = await api.finalizeGrading(currentSubjectId.value, sessionId.value)
    finalizeConfirmOpen.value = false
    toast.success('评测已定稿')
    await refreshData()
  } catch (e) {
    if (e instanceof AssessmentConflictError) {
      toast.error(`操作冲突：${e.detail || '状态已变更'}`)
      await loadSession()
    } else {
      toast.error((e as Error)?.message || '操作失败')
    }
  } finally {
    transitioning.value = false
  }
}

// -------------------------------------------------------------- 成绩册 //
const gradebook = ref<Gradebook | null>(null)
const gradebookLoading = ref(false)
const gradebookError = ref(false)
const gradebookLoaded = ref(false)
const page = ref(1)

const totalPages = computed(() => {
  const gb = gradebook.value
  if (!gb || gb.page_size <= 0) return 1
  return Math.max(1, Math.ceil(gb.total / gb.page_size))
})
const hasPrev = computed(() => page.value > 1)
const hasNext = computed(() => page.value < totalPages.value)

interface RowDraft {
  participation_id: number
  attempt_id: number | null
  attempt_revision: number
  attempt_status: string | null
  display_name: string
  identifier: string
  attendance_status: string
  participation_status: string
  values: Record<number, string>
  original: Record<number, string>
  total_score: string | null
  graded_count: number
  saving: boolean
}

const drafts = ref<RowDraft[]>([])

function scoreToInput(v: string | null): string {
  return v == null ? '' : v
}

function buildDraft(row: GradebookRow): RowDraft {
  const values: Record<number, string> = {}
  const original: Record<number, string> = {}
  for (const s of row.scores) {
    const str = scoreToInput(s.score)
    values[s.item_id] = str
    original[s.item_id] = str
  }
  return {
    participation_id: row.participation_id,
    attempt_id: row.attempt_id,
    attempt_revision: row.attempt_revision,
    attempt_status: row.attempt_status,
    display_name: row.display_name ?? '—',
    identifier: row.identifier ?? '',
    attendance_status: row.attendance_status,
    participation_status: row.participation_status,
    values,
    original,
    total_score: row.total_score,
    graded_count: row.graded_count,
    saving: false,
  }
}

function rebuildDrafts() {
  drafts.value = (gradebook.value?.participants ?? []).map(buildDraft)
}

function maxScoreOf(itemId: number): number {
  const item = gradebook.value?.items.find((i) => i.id === itemId)
  return item ? Number(item.max_score) : 0
}

// 单元格本地校验：空(清除)或 0<=score<=max 且最多两位小数。
function cellInvalid(itemId: number, raw: string): boolean {
  const v = raw.trim()
  if (v === '') return false
  if (!/^\d+(\.\d{1,2})?$/.test(v)) return true
  const num = Number(v)
  return num < 0 || num > maxScoreOf(itemId)
}

function rowEditable(draft: RowDraft): boolean {
  return (
    canEditGrades.value
    && draft.attempt_id != null
    && draft.attendance_status === 'present'
    && draft.participation_status !== 'withdrawn'
  )
}

function changedItems(draft: RowDraft): Array<{ item_id: number; score: number | null }> {
  const items: Array<{ item_id: number; score: number | null }> = []
  for (const item of gradebook.value?.items ?? []) {
    const cur = (draft.values[item.id] ?? '').trim()
    const prev = (draft.original[item.id] ?? '').trim()
    if (cur === prev) continue
    items.push({ item_id: item.id, score: cur === '' ? null : Number(cur) })
  }
  return items
}

function isRowDirty(draft: RowDraft): boolean {
  return changedItems(draft).length > 0
}

function rowHasInvalid(draft: RowDraft): boolean {
  return (gradebook.value?.items ?? []).some((item) => cellInvalid(item.id, draft.values[item.id] ?? ''))
}

function genBatchId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return 'xxxxxxxxxxxx4xxxyxxxxxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

async function saveRow(draft: RowDraft) {
  if (!currentSubjectId.value || draft.saving || draft.attempt_id == null) return
  if (rowHasInvalid(draft)) {
    toast.error('存在无效分值，请检查后再保存')
    return
  }
  const items = changedItems(draft)
  if (items.length === 0) return
  draft.saving = true
  try {
    const result = await api.appendGrades(currentSubjectId.value, draft.attempt_id, {
      expected_revision: draft.attempt_revision,
      batch_id: genBatchId(),
      items,
    })
    draft.attempt_revision = result.revision
    draft.total_score = result.total_score
    draft.graded_count = result.graded_count
    for (const g of result.grades) {
      const str = scoreToInput(g.score)
      draft.values[g.item_id] = str
      draft.original[g.item_id] = str
    }
    toast.success(`已保存 ${draft.display_name} 的成绩`)
  } catch (e) {
    if (e instanceof AssessmentConflictError) {
      toast.error(`保存冲突：${e.detail || '数据已变更'}，正在刷新`)
      await loadGradebook()
    } else {
      toast.error((e as Error)?.message || '保存失败')
    }
  } finally {
    draft.saving = false
  }
}

async function loadGradebook() {
  if (!currentSubjectId.value || !Number.isFinite(sessionId.value)) return
  gradebookLoading.value = true
  gradebookError.value = false
  try {
    gradebook.value = await api.getGradebook(currentSubjectId.value, sessionId.value, {
      page: page.value,
      pageSize: PAGE_SIZE,
    })
    page.value = gradebook.value.page
    rebuildDrafts()
    gradebookLoaded.value = true
  } catch {
    gradebookError.value = true
  } finally {
    gradebookLoading.value = false
  }
}

function goPage(next: number) {
  if (next < 1 || next > totalPages.value || next === page.value) return
  page.value = next
  loadGradebook()
}

// -------------------------------------------------------------- 题目统计 //
const statistics = ref<ItemStatistics | null>(null)
const statisticsLoading = ref(false)
const statisticsError = ref(false)
const statisticsLoaded = ref(false)

async function loadStatistics() {
  if (!currentSubjectId.value || !Number.isFinite(sessionId.value)) return
  statisticsLoading.value = true
  statisticsError.value = false
  try {
    statistics.value = await api.getItemStatistics(currentSubjectId.value, sessionId.value)
    statisticsLoaded.value = true
  } catch {
    statisticsError.value = true
  } finally {
    statisticsLoading.value = false
  }
}

function formatRate(v: string | null): string {
  if (v == null) return '—'
  const num = Number(v)
  if (Number.isNaN(num)) return v
  return `${(num * 100).toFixed(1)}%`
}

// 按需加载:进入对应 tab 时首次拉取。
watch(activeTab, (tab) => {
  if (tab === 'gradebook' && !gradebookLoaded.value && !gradebookLoading.value) loadGradebook()
  if (tab === 'statistics' && !statisticsLoaded.value && !statisticsLoading.value) loadStatistics()
})

// 数据变更(状态流转 / 导入)后刷新已加载的分页与统计。
async function refreshData() {
  await loadSession()
  if (gradebookLoaded.value) await loadGradebook()
  if (statisticsLoaded.value) await loadStatistics()
}

// -------------------------------------------------------------- Excel //
const exporting = ref(false)
const importInput = ref<HTMLInputElement | null>(null)
const importFile = ref<File | null>(null)
const importBatchId = ref<string | null>(null)
const importPreview = ref<ScoreImportPreview | null>(null)
const importDialogOpen = ref(false)
const previewingImport = ref(false)
const applyingImport = ref(false)

async function exportExcel() {
  if (!currentSubjectId.value || exporting.value) return
  exporting.value = true
  try {
    const blob = await api.exportGradebook(currentSubjectId.value, sessionId.value)
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${(session.value?.name || '评测成绩').replace(/[\\/:*?"<>|]/g, '_')}.xlsx`
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
    toast.success('成绩表已导出')
  } catch {
    toast.error('导出成绩表失败')
  } finally {
    exporting.value = false
  }
}

function selectImportFile() {
  importInput.value?.click()
}

async function handleImportFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || !currentSubjectId.value) return
  if (!file.name.toLowerCase().endsWith('.xlsx')) {
    toast.error('请选择 .xlsx 成绩文件')
    return
  }
  if (file.size > 5 * 1024 * 1024) {
    toast.error('文件过大，请确保文件小于 5MB')
    return
  }
  importFile.value = file
  importBatchId.value = genBatchId()
  importPreview.value = null
  importDialogOpen.value = true
  previewingImport.value = true
  try {
    importPreview.value = await api.previewGradeImport(currentSubjectId.value, sessionId.value, file)
  } catch (err) {
    importDialogOpen.value = false
    toast.error((err as { data?: { detail?: string } })?.data?.detail || '预检成绩文件失败')
  } finally {
    previewingImport.value = false
  }
}

async function applyImport() {
  if (
    !currentSubjectId.value
    || !importFile.value
    || !importPreview.value?.valid
    || applyingImport.value
  ) return
  applyingImport.value = true
  try {
    const result = await api.applyGradeImport(
      currentSubjectId.value,
      sessionId.value,
      importFile.value,
      importBatchId.value ?? undefined,
    )
    importDialogOpen.value = false
    toast.success(
      result.replayed
        ? '该文件已导入过，未重复写入'
        : `已导入 ${result.changed_rows} 名参与者的 ${result.changed_scores} 项成绩`,
    )
    await refreshData()
  } catch (err) {
    if (err instanceof AssessmentConflictError) {
      toast.error(`导入冲突：${err.detail}`)
      await refreshData()
    } else {
      toast.error((err as { data?: { detail?: string } })?.data?.detail || '导入成绩失败')
    }
  } finally {
    applyingImport.value = false
  }
}
</script>

<template>
  <div class="flex flex-1 flex-col">
    <header class="flex min-h-16 shrink-0 flex-wrap items-center gap-x-2 gap-y-2 border-b px-4 py-2">
      <Button variant="ghost" size="icon" class="h-8 w-8 shrink-0" @click="router.push('/assessments')">
        <ArrowLeft class="h-4 w-4" />
      </Button>
      <div class="min-w-0 flex-1 basis-48">
        <p class="truncate text-sm font-medium">{{ session?.name || '评测详情' }}</p>
        <p v-if="session" class="truncate text-xs text-muted-foreground">
          版本 v{{ session.version_no }} · 总分 {{ session.total_score ?? '—' }} · {{ session.item_count ?? 0 }} 题
        </p>
      </div>
      <template v-if="session">
        <Badge :variant="gradingMeta(session.grading_status).variant">
          {{ gradingMeta(session.grading_status).label }}
        </Badge>
        <Badge :variant="deliveryMeta(session.delivery_status).variant">
          {{ deliveryMeta(session.delivery_status).label }}
        </Badge>
      </template>
      <Button
        size="sm"
        variant="outline"
        class="shrink-0"
        :disabled="exporting || loading"
        title="导出 Excel 成绩表"
        @click="exportExcel"
      >
        <Loader2 v-if="exporting" class="h-4 w-4 animate-spin sm:mr-2" />
        <Download v-else class="h-4 w-4 sm:mr-2" />
        <span class="hidden sm:inline">导出</span>
      </Button>
      <Button
        v-if="canEditScores && isInProgress"
        size="sm"
        variant="outline"
        class="shrink-0"
        title="导入 Excel 成绩"
        @click="selectImportFile"
      >
        <Upload class="h-4 w-4 sm:mr-2" />
        <span class="hidden sm:inline">导入</span>
      </Button>
      <input ref="importInput" type="file" accept=".xlsx" class="hidden" @change="handleImportFile">
      <Button
        v-if="canEditScores && isNotStarted"
        size="sm"
        class="shrink-0"
        :disabled="transitioning"
        @click="startGrading"
      >
        <Loader2 v-if="transitioning" class="h-4 w-4 animate-spin sm:mr-2" />
        <Play v-else class="h-4 w-4 sm:mr-2" />
        <span class="hidden sm:inline">开始评分</span>
      </Button>
      <Button
        v-if="canEditScores && isInProgress"
        size="sm"
        variant="outline"
        class="shrink-0"
        :disabled="transitioning"
        @click="finalizeConfirmOpen = true"
      >
        <Lock class="h-4 w-4 sm:mr-2" />
        <span class="hidden sm:inline">定稿</span>
      </Button>
    </header>

    <div class="flex flex-1 flex-col p-4">
      <div v-if="loading" class="flex justify-center py-16">
        <Loader2 class="h-6 w-6 animate-spin text-muted-foreground" />
      </div>

      <div v-else-if="error" class="flex flex-col items-center gap-3 py-16 text-center text-sm text-muted-foreground">
        <AlertTriangle class="h-5 w-5 text-amber-500" />
        <span>加载评测失败</span>
        <Button size="sm" variant="outline" @click="loadSession">重试</Button>
      </div>

      <Tabs v-else-if="session" v-model="activeTab" class="flex flex-1 flex-col">
        <TabsList class="w-fit">
          <TabsTrigger value="overview">概览</TabsTrigger>
          <TabsTrigger value="gradebook">成绩册</TabsTrigger>
          <TabsTrigger value="statistics">题目统计</TabsTrigger>
        </TabsList>

        <!-- 概览 -->
        <TabsContent value="overview" class="flex-1 space-y-4">
          <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div class="rounded-md border p-3">
              <p class="text-xs text-muted-foreground">参与人数</p>
              <p class="text-lg font-semibold">{{ session.participants.length }}</p>
            </div>
            <div class="rounded-md border p-3">
              <p class="text-xs text-muted-foreground">题目数</p>
              <p class="text-lg font-semibold">{{ session.item_count ?? session.items.length }}</p>
            </div>
            <div class="rounded-md border p-3">
              <p class="text-xs text-muted-foreground">总分</p>
              <p class="text-lg font-semibold">{{ session.total_score ?? '—' }}</p>
            </div>
            <div class="rounded-md border p-3">
              <p class="text-xs text-muted-foreground">创建时间</p>
              <p class="truncate text-sm font-medium">{{ formatTime(session.created_at) }}</p>
            </div>
          </div>

          <div class="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead class="w-40">标识</TableHead>
                  <TableHead>姓名</TableHead>
                  <TableHead class="w-24 text-center">出勤</TableHead>
                  <TableHead class="w-28 text-center">已评分</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow v-for="p in session.participants" :key="p.id">
                  <TableCell class="font-mono text-xs text-muted-foreground">{{ p.identifier ?? '—' }}</TableCell>
                  <TableCell>{{ p.display_name ?? '—' }}</TableCell>
                  <TableCell class="text-center">
                    <Badge :variant="attendanceMeta(p.attendance_status).variant">
                      {{ attendanceMeta(p.attendance_status).label }}
                    </Badge>
                  </TableCell>
                  <TableCell class="text-center text-xs text-muted-foreground">
                    <template v-if="p.attempts.length">
                      {{ p.attempts[0]!.graded_count }} / {{ session.item_count ?? session.items.length }}
                    </template>
                    <template v-else>—</template>
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
            <p v-if="session.participants.length === 0" class="py-10 text-center text-sm text-muted-foreground">
              该场次暂无参与者。
            </p>
          </div>
        </TabsContent>

        <!-- 成绩册 -->
        <TabsContent value="gradebook" class="flex-1">
          <div v-if="gradebookLoading" class="flex justify-center py-16">
            <Loader2 class="h-6 w-6 animate-spin text-muted-foreground" />
          </div>

          <div v-else-if="gradebookError" class="flex flex-col items-center gap-3 py-16 text-center text-sm text-muted-foreground">
            <AlertTriangle class="h-5 w-5 text-amber-500" />
            <span>加载成绩册失败</span>
            <Button size="sm" variant="outline" @click="loadGradebook">重试</Button>
          </div>

          <template v-else-if="gradebook">
            <p v-if="isNotStarted" class="mb-3 rounded-md border border-dashed p-3 text-sm text-muted-foreground">
              评测尚未开始评分，请先“开始评分”后再录入成绩。
            </p>
            <p v-else-if="isFinalized" class="mb-3 rounded-md border border-dashed p-3 text-sm text-muted-foreground">
              评测已定稿，成绩为只读。
            </p>

            <div class="overflow-x-auto rounded-md border">
              <Table class="min-w-max">
                <TableHeader>
                  <TableRow>
                    <TableHead class="sticky left-0 z-20 w-32 bg-background">标识</TableHead>
                    <TableHead class="sticky left-32 z-20 w-36 bg-background">姓名</TableHead>
                    <TableHead
                      v-for="(item, i) in gradebook.items"
                      :key="item.id"
                      class="w-24 text-center"
                    >
                      <div class="flex flex-col items-center">
                        <span>第 {{ i + 1 }} 题</span>
                        <span class="text-xs font-normal text-muted-foreground">/ {{ item.max_score }}</span>
                      </div>
                    </TableHead>
                    <TableHead class="w-20 text-center">总分</TableHead>
                    <TableHead class="sticky right-0 z-20 w-20 bg-background text-center">操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  <TableRow v-for="draft in drafts" :key="draft.participation_id">
                    <TableCell class="sticky left-0 z-10 w-32 bg-background font-mono text-xs text-muted-foreground">
                      <div class="flex items-center gap-1">
                        <span class="truncate">{{ draft.identifier || '—' }}</span>
                        <Badge
                          v-if="draft.participation_status === 'withdrawn'"
                          variant="destructive"
                          class="shrink-0 text-[10px]"
                        >
                          已退出
                        </Badge>
                        <Badge
                          v-else-if="draft.attendance_status !== 'present'"
                          :variant="attendanceMeta(draft.attendance_status).variant"
                          class="shrink-0 text-[10px]"
                        >
                          {{ attendanceMeta(draft.attendance_status).label }}
                        </Badge>
                      </div>
                    </TableCell>
                    <TableCell class="sticky left-32 z-10 w-36 truncate bg-background">
                      {{ draft.display_name }}
                    </TableCell>
                    <TableCell v-for="item in gradebook.items" :key="item.id" class="w-24">
                      <Input
                        v-model="draft.values[item.id]"
                        type="text"
                        inputmode="decimal"
                        class="h-8 w-full min-w-0 text-center"
                        :class="cellInvalid(item.id, draft.values[item.id] ?? '') ? 'border-destructive focus-visible:ring-destructive' : ''"
                        :title="`满分 ${item.max_score}`"
                        :disabled="!rowEditable(draft) || draft.saving"
                      />
                    </TableCell>
                    <TableCell class="w-20 text-center font-medium">
                      {{ draft.total_score ?? '—' }}
                    </TableCell>
                    <TableCell class="sticky right-0 z-10 w-20 bg-background text-center">
                      <Button
                        size="sm"
                        variant="outline"
                        class="h-8"
                        :disabled="!rowEditable(draft) || draft.saving || !isRowDirty(draft) || rowHasInvalid(draft)"
                        @click="saveRow(draft)"
                      >
                        <Loader2 v-if="draft.saving" class="h-4 w-4 animate-spin" />
                        <Save v-else class="h-4 w-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                </TableBody>
              </Table>
            </div>

            <p v-if="drafts.length === 0" class="py-10 text-center text-sm text-muted-foreground">
              该场次暂无参与者。
            </p>

            <!-- 分页 -->
            <div v-if="drafts.length > 0" class="mt-3 flex items-center justify-between text-sm">
              <span class="text-xs text-muted-foreground">
                第 {{ gradebook.page }} / {{ totalPages }} 页 · 共 {{ gradebook.total }} 人
              </span>
              <div class="flex items-center gap-2">
                <Button size="sm" variant="outline" :disabled="!hasPrev || gradebookLoading" @click="goPage(page - 1)">
                  上一页
                </Button>
                <Button size="sm" variant="outline" :disabled="!hasNext || gradebookLoading" @click="goPage(page + 1)">
                  下一页
                </Button>
              </div>
            </div>
          </template>
        </TabsContent>

        <!-- 题目统计 -->
        <TabsContent value="statistics" class="flex-1">
          <div v-if="statisticsLoading" class="flex justify-center py-16">
            <Loader2 class="h-6 w-6 animate-spin text-muted-foreground" />
          </div>

          <div v-else-if="statisticsError" class="flex flex-col items-center gap-3 py-16 text-center text-sm text-muted-foreground">
            <AlertTriangle class="h-5 w-5 text-amber-500" />
            <span>加载题目统计失败</span>
            <Button size="sm" variant="outline" @click="loadStatistics">重试</Button>
          </div>

          <template v-else-if="statistics">
            <p class="mb-3 text-xs text-muted-foreground">
              参与人数 {{ statistics.participation_count }} · 各题“已评/参与”为统计分母。
            </p>
            <div class="overflow-x-auto rounded-md border">
              <Table class="min-w-max">
                <TableHeader>
                  <TableRow>
                    <TableHead class="w-20 text-center">序号</TableHead>
                    <TableHead>题目</TableHead>
                    <TableHead class="w-20 text-center">满分</TableHead>
                    <TableHead class="w-28 text-center">已评/参与</TableHead>
                    <TableHead class="w-24 text-center">平均分</TableHead>
                    <TableHead class="w-24 text-center">失分人数</TableHead>
                    <TableHead class="w-24 text-center">失分率</TableHead>
                    <TableHead class="w-24 text-center">满分人数</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  <TableRow v-for="(it, i) in statistics.items" :key="it.item_id">
                    <TableCell class="text-center text-muted-foreground">{{ i + 1 }}</TableCell>
                    <TableCell class="font-mono text-xs">{{ it.item_key }}</TableCell>
                    <TableCell class="text-center">{{ it.max_score }}</TableCell>
                    <TableCell class="text-center">{{ it.graded_count }} / {{ statistics.participation_count }}</TableCell>
                    <TableCell class="text-center font-medium">{{ it.average_score ?? '—' }}</TableCell>
                    <TableCell class="text-center">{{ it.incorrect_count }}</TableCell>
                    <TableCell class="text-center">{{ formatRate(it.error_rate) }}</TableCell>
                    <TableCell class="text-center">{{ it.full_marks_count }}</TableCell>
                  </TableRow>
                </TableBody>
              </Table>
              <p v-if="statistics.items.length === 0" class="py-10 text-center text-sm text-muted-foreground">
                暂无题目统计。
              </p>
            </div>
          </template>
        </TabsContent>
      </Tabs>
    </div>

    <AlertDialog v-model:open="finalizeConfirmOpen">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>定稿评测成绩？</AlertDialogTitle>
          <AlertDialogDescription>
            定稿后成绩将变为只读，无法继续录入或导入。请确认所有成绩均已录入完毕。
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel :disabled="transitioning">取消</AlertDialogCancel>
          <AlertDialogAction :disabled="transitioning" @click="confirmFinalize">
            <Loader2 v-if="transitioning" class="mr-2 h-4 w-4 animate-spin" />
            确认定稿
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>

    <Dialog v-model:open="importDialogOpen">
      <DialogContent class="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>导入成绩预检</DialogTitle>
          <DialogDescription class="truncate">
            {{ importFile?.name }}
          </DialogDescription>
        </DialogHeader>

        <div v-if="previewingImport" class="flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground">
          <Loader2 class="h-5 w-5 animate-spin" />
          正在校验成绩文件
        </div>
        <div v-else-if="importPreview" class="space-y-4">
          <div v-if="importPreview.valid" class="grid grid-cols-3 border-y py-4 text-center">
            <div>
              <p class="text-xl font-semibold">{{ importPreview.changed_rows }}</p>
              <p class="text-xs text-muted-foreground">变更参与者</p>
            </div>
            <div>
              <p class="text-xl font-semibold">{{ importPreview.changed_scores }}</p>
              <p class="text-xs text-muted-foreground">变更分数</p>
            </div>
            <div>
              <p class="text-xl font-semibold">{{ importPreview.unchanged_rows }}</p>
              <p class="text-xs text-muted-foreground">无变化</p>
            </div>
          </div>
          <div v-else class="max-h-64 overflow-y-auto border-y py-2">
            <div
              v-for="(item, index) in importPreview.errors"
              :key="`${item.row}-${item.field}-${index}`"
              class="flex gap-2 px-2 py-2 text-sm"
            >
              <AlertTriangle class="mt-0.5 h-4 w-4 shrink-0 text-amber-500" />
              <span>第 {{ item.row }} 行 · {{ item.field }}：{{ item.message }}</span>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" :disabled="applyingImport" @click="importDialogOpen = false">
            取消
          </Button>
          <Button
            :disabled="previewingImport || applyingImport || !importPreview?.valid || importPreview.changed_scores === 0"
            @click="applyImport"
          >
            <Loader2 v-if="applyingImport" class="mr-2 h-4 w-4 animate-spin" />
            <Upload v-else class="mr-2 h-4 w-4" />
            确认导入
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
