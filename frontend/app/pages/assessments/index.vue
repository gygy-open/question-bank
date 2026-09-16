<script setup lang="ts">
// 评测与成绩：某学科下的投放场次列表 + 创建入口。资源都在当前学科强上下文下。
import { ref, computed, watch, onActivated, onMounted } from 'vue'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { ClipboardCheck, Plus, Loader2, ChevronRight, AlertTriangle, Search } from '@lucide/vue'
import { toast } from 'vue-sonner'
import { useAssessments } from '~/composables/useAssessments'
import { useSubjectContext } from '~/composables/useSubjectContext'
import { Capability, usePermissions } from '~/composables/usePermissions'
import type { Assessment, Classroom, GradingStatus, Session } from '~/types/assessment'

const router = useRouter()
const route = useRoute()
const api = useAssessments()
const { currentSubjectId } = useSubjectContext()
const { can } = usePermissions()

const canManage = computed(() => can(Capability.MANAGE_ASSESSMENT, currentSubjectId.value))

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

function gradingMeta(status: string) {
  return GRADING_META[status as GradingStatus] ?? { label: status, variant: 'outline' as const }
}

function deliveryMeta(status: string) {
  return DELIVERY_META[status] ?? { label: status, variant: 'outline' as const }
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

// ------------------------------------------------------------------ 过滤 //
const ALL = '__all__'
const gradingFilter = ref<GradingStatus | typeof ALL>(ALL)
const assessmentFilter = ref<string>(ALL)
const nameSearch = ref('')

const sessions = ref<Session[]>([])
const assessments = ref<Assessment[]>([])
const classrooms = ref<Classroom[]>([])
const loading = ref(false)
const error = ref(false)

const filteredSessions = computed(() => {
  const q = nameSearch.value.trim().toLowerCase()
  if (!q) return sessions.value
  return sessions.value.filter((s) => s.name.toLowerCase().includes(q))
})

async function load() {
  if (!currentSubjectId.value) {
    sessions.value = []
    assessments.value = []
    classrooms.value = []
    return
  }
  loading.value = true
  error.value = false
  const opts: { gradingStatus?: GradingStatus; assessmentId?: number } = {}
  if (gradingFilter.value !== ALL) opts.gradingStatus = gradingFilter.value
  if (assessmentFilter.value !== ALL) {
    const id = Number(assessmentFilter.value)
    if (Number.isFinite(id)) opts.assessmentId = id
  }
  try {
    const [list, ids, rooms] = await Promise.all([
      api.listSessions(currentSubjectId.value, opts),
      api.listAssessments(currentSubjectId.value),
      api.listClassrooms(currentSubjectId.value),
    ])
    sessions.value = list
    assessments.value = ids
    classrooms.value = rooms
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}

onActivated(load)
watch(currentSubjectId, load)
watch([gradingFilter, assessmentFilter], load)

// ------------------------------------------------------------ 创建评测 //
const createOpen = ref(false)
const submitting = ref(false)
const form = ref<{
  title: string
  classroomId: string
  compositionVersionId: number | null
  sessionName: string
}>({
  title: '',
  classroomId: '',
  compositionVersionId: null,
  sessionName: '',
})

function openCreate(prefill?: { versionId?: number | null; title?: string }) {
  form.value = {
    title: prefill?.title ?? '',
    classroomId: '',
    compositionVersionId: prefill?.versionId ?? null,
    sessionName: '',
  }
  createOpen.value = true
}

function goToRosters() {
  createOpen.value = false
  router.push('/rosters')
}

// route query 携带 compositionVersionId 时自动打开并预填(可选 title)。
onMounted(() => {
  const rawId = route.query.compositionVersionId
  const rawTitle = route.query.title
  const idVal = Array.isArray(rawId) ? rawId[0] : rawId
  const titleVal = Array.isArray(rawTitle) ? rawTitle[0] : rawTitle
  const parsed = idVal != null ? Number(idVal) : NaN
  if (Number.isFinite(parsed) && parsed > 0) {
    openCreate({ versionId: parsed, title: typeof titleVal === 'string' ? titleVal : '' })
  }
})

async function submitCreate() {
  if (!currentSubjectId.value) return
  const title = form.value.title.trim()
  if (!title) {
    toast.error('请填写评测名称')
    return
  }
  const classroomId = Number(form.value.classroomId)
  if (!Number.isFinite(classroomId) || classroomId <= 0) {
    toast.error('请选择班级')
    return
  }
  const versionId = form.value.compositionVersionId
  if (versionId == null || !Number.isFinite(versionId) || versionId <= 0) {
    toast.error('请填写有效的组稿定稿版本 ID')
    return
  }
  const sessionName = form.value.sessionName.trim()
  submitting.value = true
  try {
    const created = await api.createAssessment(currentSubjectId.value, {
      title,
      composition_version_id: versionId,
      classroom_id: classroomId,
      session_name: sessionName || null,
    })
    createOpen.value = false
    toast.success('评测已创建')
    router.push(`/assessments/sessions/${created.id}`)
  } catch (e) {
    toast.error((e as Error)?.message || '创建失败')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="flex flex-1 flex-col">
    <header class="flex h-16 shrink-0 items-center gap-2 border-b px-4">
      <ClipboardCheck class="h-5 w-5 text-muted-foreground" />
      <div class="min-w-0 flex-1">
        <p class="truncate text-sm font-medium">评测与成绩</p>
      </div>
      <Button v-if="canManage" size="sm" :disabled="!currentSubjectId" @click="openCreate()">
        <Plus class="mr-2 h-4 w-4" />
        创建评测
      </Button>
    </header>

    <div class="flex flex-1 flex-col gap-4 p-4">
      <div v-if="!currentSubjectId" class="flex flex-col items-center gap-2 py-16 text-center text-sm text-muted-foreground">
        <ClipboardCheck class="h-5 w-5" />
        <span>请先选择一个学科</span>
      </div>

      <template v-else>
        <!-- 过滤工具条 -->
        <div class="flex flex-wrap items-center gap-2">
          <Select v-model="gradingFilter">
            <SelectTrigger class="w-[150px]">
              <SelectValue placeholder="评分状态" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem :value="ALL">全部评分状态</SelectItem>
              <SelectItem value="not_started">未开始</SelectItem>
              <SelectItem value="in_progress">评分中</SelectItem>
              <SelectItem value="finalized">已定稿</SelectItem>
            </SelectContent>
          </Select>
          <Select v-model="assessmentFilter">
            <SelectTrigger class="w-[200px]">
              <SelectValue placeholder="评测来源" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem :value="ALL">全部评测来源</SelectItem>
              <SelectItem v-for="a in assessments" :key="a.id" :value="String(a.id)">
                {{ a.title }}
              </SelectItem>
            </SelectContent>
          </Select>
          <div class="relative w-full sm:w-64">
            <Search class="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input v-model="nameSearch" placeholder="按名称搜索场次" class="pl-9" />
          </div>
        </div>

        <div v-if="loading" class="flex justify-center py-16">
          <Loader2 class="h-6 w-6 animate-spin text-muted-foreground" />
        </div>

        <div v-else-if="error" class="flex flex-col items-center gap-3 py-16 text-center text-sm text-muted-foreground">
          <AlertTriangle class="h-5 w-5 text-amber-500" />
          <span>加载评测列表失败</span>
          <Button size="sm" variant="outline" @click="load">重试</Button>
        </div>

        <div v-else-if="filteredSessions.length === 0" class="flex flex-col items-center gap-2 py-16 text-center text-sm text-muted-foreground">
          <ClipboardCheck class="h-5 w-5" />
          <span>{{ sessions.length === 0 ? '还没有评测场次' : '没有匹配的场次' }}</span>
          <Button v-if="canManage && sessions.length === 0" size="sm" variant="outline" @click="openCreate()">
            <Plus class="mr-2 h-4 w-4" />
            创建评测
          </Button>
        </div>

        <div v-else class="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>名称</TableHead>
                <TableHead>评测</TableHead>
                <TableHead class="w-28 text-center">评分状态</TableHead>
                <TableHead class="w-28 text-center">投放状态</TableHead>
                <TableHead class="w-48">创建时间</TableHead>
                <TableHead class="w-48">更新时间</TableHead>
                <TableHead class="w-24 text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow
                v-for="s in filteredSessions"
                :key="s.id"
                class="cursor-pointer"
                @click="router.push(`/assessments/sessions/${s.id}`)"
              >
                <TableCell class="font-medium">{{ s.name }}</TableCell>
                <TableCell class="text-sm text-muted-foreground">{{ s.assessment_title ?? '—' }}</TableCell>
                <TableCell class="text-center">
                  <Badge :variant="gradingMeta(s.grading_status).variant">
                    {{ gradingMeta(s.grading_status).label }}
                  </Badge>
                </TableCell>
                <TableCell class="text-center">
                  <Badge :variant="deliveryMeta(s.delivery_status).variant">
                    {{ deliveryMeta(s.delivery_status).label }}
                  </Badge>
                </TableCell>
                <TableCell class="text-xs text-muted-foreground">{{ formatTime(s.created_at) }}</TableCell>
                <TableCell class="text-xs text-muted-foreground">{{ formatTime(s.updated_at) }}</TableCell>
                <TableCell class="text-right">
                  <Button variant="ghost" size="sm" class="h-8" @click.stop="router.push(`/assessments/sessions/${s.id}`)">
                    进入
                    <ChevronRight class="ml-1 h-3.5 w-3.5" />
                  </Button>
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>
      </template>
    </div>

    <!-- 创建评测 -->
    <Dialog v-model:open="createOpen">
      <DialogContent class="sm:max-w-[460px]">
        <DialogHeader>
          <DialogTitle>创建评测</DialogTitle>
          <DialogDescription>基于一个已定稿的组稿版本，为某个班级创建一场评测。</DialogDescription>
        </DialogHeader>
        <div class="space-y-4 py-2">
          <div class="space-y-2">
            <Label for="assessment-title">评测名称</Label>
            <Input id="assessment-title" v-model="form.title" placeholder="例如：第一次月考" @keyup.enter="submitCreate" />
          </div>
          <div class="space-y-2">
            <Label>班级</Label>
            <Select v-model="form.classroomId">
              <SelectTrigger>
                <SelectValue placeholder="选择班级" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem v-for="c in classrooms" :key="c.id" :value="String(c.id)">
                  {{ c.name }}
                </SelectItem>
              </SelectContent>
            </Select>
            <p v-if="classrooms.length === 0" class="text-xs text-muted-foreground">
              当前学科还没有班级，
              <Button
                variant="link"
                size="sm"
                class="h-auto p-0 text-xs"
                @click="goToRosters"
              >
                去名册中创建班级
              </Button>
            </p>
          </div>
          <div class="space-y-2">
            <Label for="assessment-version">组稿定稿版本 ID</Label>
            <Input
              id="assessment-version"
              v-model.number="form.compositionVersionId"
              type="number"
              min="1"
              step="1"
              placeholder="组稿定稿版本的 ID"
            />
            <p class="text-xs text-muted-foreground">
              从组稿版本预览页点击“创建评测”可自动带入此 ID。
            </p>
          </div>
          <div class="space-y-2">
            <Label for="assessment-session-name">场次名称（可选）</Label>
            <Input
              id="assessment-session-name"
              v-model="form.sessionName"
              placeholder="留空则使用默认场次名"
              @keyup.enter="submitCreate"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="createOpen = false">取消</Button>
          <Button :disabled="submitting" @click="submitCreate">
            <Loader2 v-if="submitting" class="mr-2 h-4 w-4 animate-spin" />
            创建
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
