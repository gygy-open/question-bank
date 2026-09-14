<script setup lang="ts">
// 考试与成绩：某学科下的考试列表 + 创建入口。资源都在当前学科强上下文下。
import { ref, computed, watch, onMounted } from 'vue'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
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
import { ClipboardCheck, Plus, Loader2, ChevronRight, AlertTriangle } from '@lucide/vue'
import { toast } from 'vue-sonner'
import { useAssessments } from '~/composables/useAssessments'
import { useSubjectContext } from '~/composables/useSubjectContext'
import { Capability, usePermissions } from '~/composables/usePermissions'
import type { Classroom, ExamSession, ExamSessionStatus } from '~/types/assessment'

const router = useRouter()
const route = useRoute()
const api = useAssessments()
const { currentSubjectId } = useSubjectContext()
const { can } = usePermissions()

const canManage = computed(() => can(Capability.MANAGE_ASSESSMENT, currentSubjectId.value))

const sessions = ref<ExamSession[]>([])
const classrooms = ref<Classroom[]>([])
const loading = ref(false)
const error = ref(false)

const classroomNameById = computed(() => {
  const map = new Map<number, string>()
  for (const c of classrooms.value) map.set(c.id, c.name)
  return map
})

const STATUS_META: Record<ExamSessionStatus, { label: string; variant: 'secondary' | 'default' | 'outline' }> = {
  draft: { label: '草稿', variant: 'outline' },
  recording: { label: '录入中', variant: 'default' },
  locked: { label: '已锁定', variant: 'secondary' },
  archived: { label: '已归档', variant: 'secondary' },
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

async function load() {
  if (!currentSubjectId.value) {
    sessions.value = []
    classrooms.value = []
    return
  }
  loading.value = true
  error.value = false
  try {
    const [list, rooms] = await Promise.all([
      api.listExamSessions(currentSubjectId.value),
      api.listClassrooms(currentSubjectId.value),
    ])
    sessions.value = list
    classrooms.value = rooms
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(currentSubjectId, load)

// ------------------------------------------------------------ 创建考试 //
const createOpen = ref(false)
const submitting = ref(false)
const form = ref<{ name: string; classroomId: string; compositionVersionId: number | null }>({
  name: '',
  classroomId: '',
  compositionVersionId: null,
})

function openCreate(prefillVersionId?: number | null) {
  form.value = {
    name: '',
    classroomId: '',
    compositionVersionId: prefillVersionId ?? null,
  }
  createOpen.value = true
}

function goToRosters() {
  createOpen.value = false
  router.push('/rosters')
}

// route query 携带 compositionVersionId 时自动打开并预填。
onMounted(() => {
  const raw = route.query.compositionVersionId
  const val = Array.isArray(raw) ? raw[0] : raw
  const parsed = val != null ? Number(val) : NaN
  if (Number.isFinite(parsed) && parsed > 0) openCreate(parsed)
})

async function submitCreate() {
  if (!currentSubjectId.value) return
  const name = form.value.name.trim()
  if (!name) {
    toast.error('请填写考试名称')
    return
  }
  const classroomId = Number(form.value.classroomId)
  if (!Number.isFinite(classroomId) || classroomId <= 0) {
    toast.error('请选择班级')
    return
  }
  const versionId = form.value.compositionVersionId
  if (versionId == null || !Number.isFinite(versionId) || versionId <= 0) {
    toast.error('请填写有效的组稿版本 ID')
    return
  }
  submitting.value = true
  try {
    const created = await api.createExamSession(currentSubjectId.value, {
      name,
      classroom_id: classroomId,
      composition_version_id: versionId,
    })
    createOpen.value = false
    toast.success('考试已创建')
    router.push(`/exams/${created.id}`)
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
        <p class="truncate text-sm font-medium">考试与成绩</p>
      </div>
      <Button v-if="canManage" size="sm" :disabled="!currentSubjectId" @click="openCreate()">
        <Plus class="mr-2 h-4 w-4" />
        创建考试
      </Button>
    </header>

    <div class="flex flex-1 flex-col gap-4 p-4">
      <div v-if="!currentSubjectId" class="flex flex-col items-center gap-2 py-16 text-center text-sm text-muted-foreground">
        <ClipboardCheck class="h-5 w-5" />
        <span>请先选择一个学科</span>
      </div>

      <div v-else-if="loading" class="flex justify-center py-16">
        <Loader2 class="h-6 w-6 animate-spin text-muted-foreground" />
      </div>

      <div v-else-if="error" class="flex flex-col items-center gap-3 py-16 text-center text-sm text-muted-foreground">
        <AlertTriangle class="h-5 w-5 text-amber-500" />
        <span>加载考试列表失败</span>
        <Button size="sm" variant="outline" @click="load">重试</Button>
      </div>

      <div v-else-if="sessions.length === 0" class="flex flex-col items-center gap-2 py-16 text-center text-sm text-muted-foreground">
        <ClipboardCheck class="h-5 w-5" />
        <span>还没有考试</span>
        <Button v-if="canManage" size="sm" variant="outline" @click="openCreate()">
          <Plus class="mr-2 h-4 w-4" />
          创建考试
        </Button>
      </div>

      <div v-else class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Card
          v-for="s in sessions"
          :key="s.id"
          class="cursor-pointer transition-colors hover:border-primary/50"
          @click="router.push(`/exams/${s.id}`)"
        >
          <CardContent class="flex flex-col gap-3 p-4">
            <div class="flex items-start justify-between gap-2">
              <p class="min-w-0 flex-1 truncate font-medium">{{ s.name }}</p>
              <Badge :variant="STATUS_META[s.status].variant">{{ STATUS_META[s.status].label }}</Badge>
            </div>
            <div class="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
              <span>总分 {{ s.total_score }}</span>
              <span>班级 {{ classroomNameById.get(s.classroom_id) ?? `#${s.classroom_id}` }}</span>
              <span>创建 {{ formatTime(s.created_at) }}</span>
            </div>
            <div class="flex items-center justify-end text-xs text-primary">
              进入 <ChevronRight class="h-3.5 w-3.5" />
            </div>
          </CardContent>
        </Card>
      </div>
    </div>

    <!-- 创建考试 -->
    <Dialog v-model:open="createOpen">
      <DialogContent class="sm:max-w-[460px]">
        <DialogHeader>
          <DialogTitle>创建考试</DialogTitle>
          <DialogDescription>基于一个已定稿的组稿版本，为某个班级创建一场考试。</DialogDescription>
        </DialogHeader>
        <div class="space-y-4 py-2">
          <div class="space-y-2">
            <Label for="exam-name">考试名称</Label>
            <Input id="exam-name" v-model="form.name" placeholder="例如：第一次月考" @keyup.enter="submitCreate" />
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
            <Label for="exam-version">组稿版本 ID</Label>
            <Input
              id="exam-version"
              v-model.number="form.compositionVersionId"
              type="number"
              min="1"
              step="1"
              placeholder="组稿定稿版本的 ID"
            />
            <p class="text-xs text-muted-foreground">
              从组稿版本预览页点击“创建考试”可自动带入此 ID。
            </p>
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
