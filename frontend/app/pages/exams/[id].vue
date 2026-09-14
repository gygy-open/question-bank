<script setup lang="ts">
// 考试详情 + 成绩录入。逐题录分，只提交相较已加载行发生变化的题目；
// 乐观锁冲突(409)统一 toast 后重载 gradebook。资源在当前学科强上下文下。
import { ref, computed, watch, onMounted } from 'vue'
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
  ExamSessionDetail,
  ExamSessionStatus,
  Gradebook,
  GradebookRow,
  Result,
  ScoreItemInput,
  ScoreImportPreview,
} from '~/types/assessment'

const route = useRoute()
const router = useRouter()
const api = useAssessments()
const { currentSubjectId } = useSubjectContext()
const { can } = usePermissions()

const examSessionId = computed(() => Number(route.params.id))
const canManage = computed(() => can(Capability.MANAGE_ASSESSMENT, currentSubjectId.value))
const canEditScores = computed(() => can(Capability.EDIT_SCORE, currentSubjectId.value))

const session = ref<ExamSessionDetail | null>(null)
const gradebook = ref<Gradebook | null>(null)
const loading = ref(false)
const error = ref(false)
const transitioning = ref(false)
const lockConfirmOpen = ref(false)
const importDialogOpen = ref(false)
const importInput = ref<HTMLInputElement | null>(null)
const importFile = ref<File | null>(null)
const importPreview = ref<ScoreImportPreview | null>(null)
const exporting = ref(false)
const previewingImport = ref(false)
const applyingImport = ref(false)

const STATUS_META: Record<ExamSessionStatus, { label: string; variant: 'secondary' | 'default' | 'outline' }> = {
  draft: { label: '草稿', variant: 'outline' },
  recording: { label: '录入中', variant: 'default' },
  locked: { label: '已锁定', variant: 'secondary' },
  archived: { label: '已归档', variant: 'secondary' },
}

const status = computed<ExamSessionStatus | null>(() => gradebook.value?.status ?? session.value?.status ?? null)
const isRecording = computed(() => status.value === 'recording')
const isDraft = computed(() => status.value === 'draft')
const inputDisabled = computed(() => !canEditScores.value || !isRecording.value)

// -------------------------------------------------------- 逐行草稿 //
interface RowDraft {
  participant_id: number
  result_id: number
  student_id: number | null
  name: string
  student_no: string
  values: Record<number, string> // exam_question_id -> 输入字符串
  original: Record<number, string> // 已加载快照，用于计算差异
  revision: number
  total_score: string | null
  is_complete: boolean
  saving: boolean
}

const drafts = ref<RowDraft[]>([])

function scoreToInput(v: string | null): string {
  return v == null ? '' : v
}

function buildDraft(row: GradebookRow): RowDraft {
  const values: Record<number, string> = {}
  const original: Record<number, string> = {}
  for (const item of row.scores) {
    const s = scoreToInput(item.score)
    values[item.exam_question_id] = s
    original[item.exam_question_id] = s
  }
  return {
    participant_id: row.participant_id,
    result_id: row.result_id,
    student_id: row.student_id,
    name: row.name,
    student_no: row.student_no,
    values,
    original,
    revision: row.revision,
    total_score: row.total_score,
    is_complete: row.is_complete,
    saving: false,
  }
}

function rebuildDrafts() {
  drafts.value = (gradebook.value?.participants ?? []).map(buildDraft)
}

function changedItems(draft: RowDraft): ScoreItemInput[] {
  const items: ScoreItemInput[] = []
  for (const q of gradebook.value?.questions ?? []) {
    const cur = (draft.values[q.id] ?? '').trim()
    const prev = (draft.original[q.id] ?? '').trim()
    if (cur === prev) continue
    items.push({ exam_question_id: q.id, score: cur === '' ? null : Number(cur) })
  }
  return items
}

function isRowDirty(draft: RowDraft): boolean {
  return changedItems(draft).length > 0
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

function applyResult(draft: RowDraft, result: Result) {
  draft.revision = result.revision
  draft.total_score = result.total_score
  draft.is_complete = result.is_complete
  for (const item of result.scores) {
    const s = scoreToInput(item.score)
    draft.values[item.exam_question_id] = s
    draft.original[item.exam_question_id] = s
  }
}

async function saveRow(draft: RowDraft) {
  if (!currentSubjectId.value || draft.saving) return
  const items = changedItems(draft)
  if (items.length === 0) return
  // 校验非法输入(NaN)。
  const invalid = items.some((it) => it.score != null && Number.isNaN(it.score as number))
  if (invalid) {
    toast.error('存在无效分值')
    return
  }
  draft.saving = true
  try {
    const result = await api.saveScores(
      currentSubjectId.value,
      examSessionId.value,
      draft.result_id,
      {
        expected_revision: draft.revision,
        batch_id: genBatchId(),
        items,
      },
    )
    applyResult(draft, result)
    toast.success(`已保存 ${draft.name} 的成绩`)
  } catch (e) {
    if (e instanceof AssessmentConflictError) {
      toast.error(`保存冲突：${e.detail || '数据已变更'}，正在刷新`)
      await load()
    } else {
      toast.error((e as Error)?.message || '保存失败')
    }
  } finally {
    draft.saving = false
  }
}

async function exportExcel() {
  if (!currentSubjectId.value || exporting.value) return
  exporting.value = true
  try {
    const blob = await api.exportGradebook(currentSubjectId.value, examSessionId.value)
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${(session.value?.name || '考试成绩').replace(/[\\/:*?"<>|]/g, '_')}.xlsx`
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
  importPreview.value = null
  importDialogOpen.value = true
  previewingImport.value = true
  try {
    importPreview.value = await api.previewScoreImport(
      currentSubjectId.value,
      examSessionId.value,
      file,
    )
  } catch (error) {
    importDialogOpen.value = false
    toast.error((error as { data?: { detail?: string } })?.data?.detail || '预检成绩文件失败')
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
    const result = await api.applyScoreImport(
      currentSubjectId.value,
      examSessionId.value,
      importFile.value,
      genBatchId(),
    )
    importDialogOpen.value = false
    await load()
    toast.success(`已导入 ${result.updated_rows} 名学生的 ${result.updated_scores} 项成绩`)
  } catch (error) {
    if (error instanceof AssessmentConflictError) {
      toast.error(`导入冲突：${error.detail}`)
      await load()
    } else {
      toast.error((error as { data?: { detail?: string } })?.data?.detail || '导入成绩失败')
    }
  } finally {
    applyingImport.value = false
  }
}

// -------------------------------------------------------- 加载 / 状态流转 //
async function load() {
  if (!currentSubjectId.value || !Number.isFinite(examSessionId.value)) return
  loading.value = true
  error.value = false
  try {
    const [detail, book] = await Promise.all([
      api.getExamSession(currentSubjectId.value, examSessionId.value),
      api.getGradebook(currentSubjectId.value, examSessionId.value),
    ])
    session.value = detail
    gradebook.value = book
    rebuildDrafts()
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch([currentSubjectId, examSessionId], load)

async function startRecording() {
  if (!currentSubjectId.value || transitioning.value) return
  transitioning.value = true
  try {
    session.value = await api.startRecording(currentSubjectId.value, examSessionId.value)
    await load()
    toast.success('已开始成绩录入')
  } catch (e) {
    if (e instanceof AssessmentConflictError) {
      toast.error(`操作冲突：${e.detail || '状态已变更'}`)
      await load()
    } else {
      toast.error((e as Error)?.message || '操作失败')
    }
  } finally {
    transitioning.value = false
  }
}

async function confirmLock() {
  if (!currentSubjectId.value || transitioning.value) return
  transitioning.value = true
  try {
    session.value = await api.lockExamSession(currentSubjectId.value, examSessionId.value)
    lockConfirmOpen.value = false
    await load()
    toast.success('考试已锁定')
  } catch (e) {
    if (e instanceof AssessmentConflictError) {
      toast.error(`操作冲突：${e.detail || '状态已变更'}`)
      await load()
    } else {
      toast.error((e as Error)?.message || '操作失败')
    }
  } finally {
    transitioning.value = false
  }
}
</script>

<template>
  <div class="flex flex-1 flex-col">
    <header class="flex h-16 shrink-0 items-center gap-2 border-b px-4">
      <Button variant="ghost" size="icon" class="h-8 w-8" @click="router.push('/exams')">
        <ArrowLeft class="h-4 w-4" />
      </Button>
      <div class="min-w-0 flex-1">
        <p class="truncate text-sm font-medium">{{ session?.name || '考试详情' }}</p>
        <p v-if="session" class="truncate text-xs text-muted-foreground">总分 {{ session.total_score }}</p>
      </div>
      <Badge v-if="status" :variant="STATUS_META[status].variant">{{ STATUS_META[status].label }}</Badge>
      <Button
        size="sm"
        variant="outline"
        :disabled="exporting || loading"
        title="导出 Excel 成绩表"
        @click="exportExcel"
      >
        <Loader2 v-if="exporting" class="mr-2 h-4 w-4 animate-spin" />
        <Download v-else class="mr-2 h-4 w-4" />
        导出
      </Button>
      <Button
        v-if="canEditScores && isRecording"
        size="sm"
        variant="outline"
        title="导入 Excel 成绩"
        @click="selectImportFile"
      >
        <Upload class="mr-2 h-4 w-4" />
        导入
      </Button>
      <input
        ref="importInput"
        type="file"
        accept=".xlsx"
        class="hidden"
        @change="handleImportFile"
      >
      <Button
        v-if="canManage && isDraft"
        size="sm"
        :disabled="transitioning"
        @click="startRecording"
      >
        <Loader2 v-if="transitioning" class="mr-2 h-4 w-4 animate-spin" />
        <Play v-else class="mr-2 h-4 w-4" />
        开始录入
      </Button>
      <Button
        v-if="canManage && isRecording"
        size="sm"
        variant="outline"
        :disabled="transitioning"
        @click="lockConfirmOpen = true"
      >
        <Lock class="mr-2 h-4 w-4" />
        锁定成绩
      </Button>
    </header>

    <div class="flex flex-1 flex-col p-4">
      <div v-if="loading" class="flex justify-center py-16">
        <Loader2 class="h-6 w-6 animate-spin text-muted-foreground" />
      </div>

      <div v-else-if="error" class="flex flex-col items-center gap-3 py-16 text-center text-sm text-muted-foreground">
        <AlertTriangle class="h-5 w-5 text-amber-500" />
        <span>加载考试失败</span>
        <Button size="sm" variant="outline" @click="load">重试</Button>
      </div>

      <Tabs v-else-if="gradebook" default-value="scores" class="flex flex-1 flex-col">
        <TabsList class="w-fit">
          <TabsTrigger value="scores">成绩录入</TabsTrigger>
          <TabsTrigger value="roster">名单</TabsTrigger>
        </TabsList>

        <!-- 成绩录入 -->
        <TabsContent value="scores" class="flex-1">
          <p v-if="isDraft" class="mb-3 rounded-md border border-dashed p-3 text-sm text-muted-foreground">
            考试仍为草稿状态，请先“开始录入”后再填写成绩。
          </p>
          <p v-else-if="!isRecording" class="mb-3 rounded-md border border-dashed p-3 text-sm text-muted-foreground">
            考试已锁定，成绩为只读。
          </p>

          <div class="overflow-x-auto rounded-md border">
            <Table class="min-w-max">
              <TableHeader>
                <TableRow>
                  <TableHead class="sticky left-0 z-20 w-28 bg-background">学号</TableHead>
                  <TableHead class="sticky left-28 z-20 w-32 bg-background">姓名</TableHead>
                  <TableHead
                    v-for="(q, i) in gradebook.questions"
                    :key="q.id"
                    class="w-24 text-center"
                  >
                    <div class="flex flex-col items-center">
                      <span>第 {{ i + 1 }} 题</span>
                      <span class="text-xs font-normal text-muted-foreground">/ {{ q.max_score }}</span>
                    </div>
                  </TableHead>
                  <TableHead class="w-20 text-center">总分</TableHead>
                  <TableHead class="w-20 text-center">状态</TableHead>
                  <TableHead class="w-24 text-center">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow v-for="draft in drafts" :key="draft.participant_id">
                  <TableCell class="sticky left-0 z-10 w-28 bg-background font-mono text-xs">
                    {{ draft.student_no }}
                  </TableCell>
                  <TableCell class="sticky left-28 z-10 w-32 truncate bg-background">
                    {{ draft.name }}
                  </TableCell>
                  <TableCell v-for="q in gradebook.questions" :key="q.id" class="w-24">
                    <Input
                      v-model="draft.values[q.id]"
                      type="number"
                      min="0"
                      :max="q.max_score"
                      step="0.5"
                      inputmode="decimal"
                      class="h-8 text-center"
                      :title="`满分 ${q.max_score}`"
                      :disabled="inputDisabled || draft.saving"
                    />
                  </TableCell>
                  <TableCell class="w-20 text-center font-medium">
                    {{ draft.total_score ?? '—' }}
                  </TableCell>
                  <TableCell class="w-20 text-center">
                    <CheckCircle2 v-if="draft.is_complete" class="mx-auto h-4 w-4 text-emerald-500" />
                    <span v-else class="text-xs text-muted-foreground">未完成</span>
                  </TableCell>
                  <TableCell class="w-24 text-center">
                    <Button
                      size="sm"
                      variant="outline"
                      class="h-8"
                      :disabled="inputDisabled || draft.saving || !isRowDirty(draft)"
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
            该考试暂无参与者。
          </p>
        </TabsContent>

        <!-- 名单 -->
        <TabsContent value="roster" class="flex-1">
          <div class="overflow-x-auto rounded-md border">
            <Table class="min-w-max">
              <TableHeader>
                <TableRow>
                  <TableHead class="w-28">学号</TableHead>
                  <TableHead class="w-40">姓名</TableHead>
                  <TableHead class="w-24 text-center">出勤</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow v-for="p in session?.participants ?? []" :key="p.id">
                  <TableCell class="font-mono text-xs">{{ p.student_no }}</TableCell>
                  <TableCell>{{ p.name }}</TableCell>
                  <TableCell class="text-center">
                    <Badge :variant="p.attendance_status === 'present' ? 'default' : 'secondary'">
                      {{ p.attendance_status === 'present' ? '出席' : '缺席' }}
                    </Badge>
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </div>
          <p v-if="(session?.participants ?? []).length === 0" class="py-10 text-center text-sm text-muted-foreground">
            该考试暂无参与者。
          </p>
        </TabsContent>
      </Tabs>
    </div>

    <AlertDialog v-model:open="lockConfirmOpen">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>锁定考试成绩？</AlertDialogTitle>
          <AlertDialogDescription>
            锁定后成绩将变为只读，无法继续录入或修改。请确认所有成绩均已录入完毕。
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel :disabled="transitioning">取消</AlertDialogCancel>
          <AlertDialogAction :disabled="transitioning" @click="confirmLock">
            <Loader2 v-if="transitioning" class="mr-2 h-4 w-4 animate-spin" />
            确认锁定
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
              <p class="text-xs text-muted-foreground">变更学生</p>
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
