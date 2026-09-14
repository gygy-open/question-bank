<script setup lang="ts">
// 学生与班级名册管理：某学科下的学生名册、班级列表与所选班级成员编辑。
// 资源都在当前学科强上下文下；VIEW_ASSESSMENT 可查看，MANAGE_ASSESSMENT 才可编辑。
import { ref, computed, watch, onMounted } from 'vue'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Users,
  UserPlus,
  Plus,
  Loader2,
  AlertTriangle,
  Search,
  Save,
} from '@lucide/vue'
import { toast } from 'vue-sonner'
import { useAssessments } from '~/composables/useAssessments'
import { useSubjectContext } from '~/composables/useSubjectContext'
import { Capability, usePermissions } from '~/composables/usePermissions'
import type { Classroom, Student } from '~/types/assessment'

const STUDENT_PAGE_SIZE = 200

const api = useAssessments()
const { currentSubjectId } = useSubjectContext()
const { can } = usePermissions()

const canManage = computed(() => can(Capability.MANAGE_ASSESSMENT, currentSubjectId.value))

// ---------------------------------------------------------------- 名册数据 //
const students = ref<Student[]>([])
const studentsTotal = ref(0)
const classrooms = ref<Classroom[]>([])
const selectedClassroomId = ref<number | null>(null)

const loadingRoster = ref(false)
const rosterError = ref(false)

const studentsTruncated = computed(() => studentsTotal.value > students.value.length)

async function reloadStudents() {
  if (!currentSubjectId.value) return
  const page = await api.listStudents(currentSubjectId.value, { pageSize: STUDENT_PAGE_SIZE })
  students.value = page.items
  studentsTotal.value = page.total
}

async function loadRoster() {
  if (!currentSubjectId.value) {
    students.value = []
    studentsTotal.value = 0
    classrooms.value = []
    selectedClassroomId.value = null
    return
  }
  loadingRoster.value = true
  rosterError.value = false
  try {
    const [page, rooms] = await Promise.all([
      api.listStudents(currentSubjectId.value, { pageSize: STUDENT_PAGE_SIZE }),
      api.listClassrooms(currentSubjectId.value),
    ])
    students.value = page.items
    studentsTotal.value = page.total
    classrooms.value = rooms
    if (rooms.length) {
      const keep = rooms.some((r) => r.id === selectedClassroomId.value)
      selectedClassroomId.value = keep ? selectedClassroomId.value : (rooms[0]?.id ?? null)
    } else {
      selectedClassroomId.value = null
    }
  } catch {
    rosterError.value = true
  } finally {
    loadingRoster.value = false
  }
}

onMounted(loadRoster)
watch(currentSubjectId, loadRoster)

// -------------------------------------------------------------- 学生名册表 //
const studentSearch = ref('')

const filteredStudents = computed(() => {
  const q = studentSearch.value.trim().toLowerCase()
  if (!q) return students.value
  return students.value.filter(
    (s) => s.name.toLowerCase().includes(q) || s.student_no.toLowerCase().includes(q),
  )
})

const classroomNameById = computed(() => {
  const map = new Map<number, string>()
  for (const c of classrooms.value) map.set(c.id, c.name)
  return map
})

// ------------------------------------------------------------ 班级成员编辑 //
const currentMembers = ref<Student[]>([])
const baselineIds = ref<Set<number>>(new Set())
const selectedIds = ref<Set<number>>(new Set())
const loadingMembers = ref(false)
const membersError = ref(false)
const savingMembers = ref(false)

const memberSearch = ref('')

const dirty = computed(() => {
  if (selectedIds.value.size !== baselineIds.value.size) return true
  for (const id of selectedIds.value) if (!baselineIds.value.has(id)) return true
  return false
})

const editorStudents = computed(() => {
  const q = memberSearch.value.trim().toLowerCase()
  if (!q) return students.value
  return students.value.filter(
    (s) => s.name.toLowerCase().includes(q) || s.student_no.toLowerCase().includes(q),
  )
})

const selectedClassroom = computed(
  () => classrooms.value.find((c) => c.id === selectedClassroomId.value) ?? null,
)

async function loadMembers(classroomId: number) {
  if (!currentSubjectId.value) return
  loadingMembers.value = true
  membersError.value = false
  try {
    const members = await api.listClassroomStudents(currentSubjectId.value, classroomId)
    currentMembers.value = members
    const ids = new Set(members.map((m) => m.id))
    baselineIds.value = ids
    selectedIds.value = new Set(ids)
  } catch {
    membersError.value = true
  } finally {
    loadingMembers.value = false
  }
}

watch(selectedClassroomId, (id) => {
  currentMembers.value = []
  baselineIds.value = new Set()
  selectedIds.value = new Set()
  memberSearch.value = ''
  if (id != null) loadMembers(id)
})

function selectClassroom(id: number) {
  if (id === selectedClassroomId.value) return
  if (dirty.value && !window.confirm('当前班级成员有未保存的更改，切换将丢失。是否继续？')) return
  selectedClassroomId.value = id
}

function toggleStudent(id: number, checked: boolean) {
  const next = new Set(selectedIds.value)
  if (checked) next.add(id)
  else next.delete(id)
  selectedIds.value = next
}

function resetSelection() {
  selectedIds.value = new Set(baselineIds.value)
}

async function saveMembers() {
  if (!currentSubjectId.value || selectedClassroomId.value == null) return
  savingMembers.value = true
  try {
    const members = await api.replaceClassroomMembers(
      currentSubjectId.value,
      selectedClassroomId.value,
      { student_ids: Array.from(selectedIds.value) },
    )
    currentMembers.value = members
    const ids = new Set(members.map((m) => m.id))
    baselineIds.value = ids
    selectedIds.value = new Set(ids)
    toast.success('班级成员已保存')
  } catch (e) {
    toast.error((e as Error)?.message || '保存失败')
  } finally {
    savingMembers.value = false
  }
}

// -------------------------------------------------------------- 创建学生 //
const createStudentOpen = ref(false)
const studentForm = ref<{ student_no: string; name: string }>({ student_no: '', name: '' })
const creatingStudent = ref(false)

function openCreateStudent() {
  studentForm.value = { student_no: '', name: '' }
  createStudentOpen.value = true
}

async function submitCreateStudent() {
  if (!currentSubjectId.value) return
  const studentNo = studentForm.value.student_no.trim()
  const name = studentForm.value.name.trim()
  if (!studentNo) {
    toast.error('请填写学号')
    return
  }
  if (!name) {
    toast.error('请填写姓名')
    return
  }
  creatingStudent.value = true
  try {
    await api.createStudent(currentSubjectId.value, { student_no: studentNo, name })
    toast.success('学生已创建')
    studentForm.value = { student_no: '', name: '' }
    await reloadStudents()
  } catch (e) {
    toast.error((e as Error)?.message || '创建失败')
  } finally {
    creatingStudent.value = false
  }
}

// -------------------------------------------------------------- 创建班级 //
const createClassroomOpen = ref(false)
const classroomName = ref('')
const creatingClassroom = ref(false)

function openCreateClassroom() {
  classroomName.value = ''
  createClassroomOpen.value = true
}

async function submitCreateClassroom() {
  if (!currentSubjectId.value) return
  const name = classroomName.value.trim()
  if (!name) {
    toast.error('请填写班级名称')
    return
  }
  creatingClassroom.value = true
  try {
    const created = await api.createClassroom(currentSubjectId.value, { name })
    classrooms.value = [...classrooms.value, created]
    createClassroomOpen.value = false
    classroomName.value = ''
    selectClassroom(created.id)
    toast.success('班级已创建')
  } catch (e) {
    toast.error((e as Error)?.message || '创建失败')
  } finally {
    creatingClassroom.value = false
  }
}
</script>

<template>
  <div class="flex flex-1 flex-col">
    <header class="flex h-16 shrink-0 items-center gap-2 border-b px-4">
      <Users class="h-5 w-5 text-muted-foreground" />
      <div class="min-w-0 flex-1">
        <p class="truncate text-sm font-medium">学生与班级</p>
      </div>
      <template v-if="canManage && currentSubjectId">
        <Button size="sm" variant="outline" @click="openCreateClassroom">
          <Plus class="mr-2 h-4 w-4" />
          创建班级
        </Button>
        <Button size="sm" @click="openCreateStudent">
          <UserPlus class="mr-2 h-4 w-4" />
          创建学生
        </Button>
      </template>
    </header>

    <div class="flex flex-1 flex-col gap-4 p-4">
      <div
        v-if="!currentSubjectId"
        class="flex flex-col items-center gap-2 py-16 text-center text-sm text-muted-foreground"
      >
        <Users class="h-5 w-5" />
        <span>请先选择一个学科</span>
      </div>

      <div v-else-if="loadingRoster" class="flex justify-center py-16">
        <Loader2 class="h-6 w-6 animate-spin text-muted-foreground" />
      </div>

      <div
        v-else-if="rosterError"
        class="flex flex-col items-center gap-3 py-16 text-center text-sm text-muted-foreground"
      >
        <AlertTriangle class="h-5 w-5 text-amber-500" />
        <span>加载名册失败</span>
        <Button size="sm" variant="outline" @click="loadRoster">重试</Button>
      </div>

      <template v-else>
        <!-- 班级列表 + 成员编辑 -->
        <div class="grid gap-4 lg:grid-cols-[260px_1fr]">
          <!-- 班级列表：小屏在上，大屏在左 -->
          <div class="flex flex-col gap-2">
            <div class="flex items-center justify-between">
              <h2 class="text-sm font-medium">班级</h2>
              <span class="text-xs text-muted-foreground">{{ classrooms.length }} 个</span>
            </div>
            <div
              v-if="classrooms.length === 0"
              class="rounded-md border border-dashed p-4 text-center text-xs text-muted-foreground"
            >
              还没有班级
              <Button
                v-if="canManage"
                variant="link"
                size="sm"
                class="h-auto p-0 pl-1 text-xs"
                @click="openCreateClassroom"
              >
                去创建
              </Button>
            </div>
            <div v-else class="flex flex-wrap gap-2 lg:flex-col">
              <button
                v-for="c in classrooms"
                :key="c.id"
                type="button"
                class="flex items-center justify-between gap-2 rounded-md border px-3 py-2 text-left text-sm transition-colors hover:bg-accent"
                :class="c.id === selectedClassroomId ? 'border-primary bg-primary/10 text-primary' : ''"
                @click="selectClassroom(c.id)"
              >
                <span class="min-w-0 flex-1 truncate">{{ c.name }}</span>
                <Badge
                  v-if="c.id === selectedClassroomId && dirty"
                  variant="outline"
                  class="shrink-0 text-[10px]"
                >
                  未保存
                </Badge>
              </button>
            </div>
          </div>

          <!-- 所选班级成员管理 -->
          <div class="flex min-w-0 flex-col gap-3">
            <div
              v-if="!selectedClassroom"
              class="flex flex-col items-center gap-2 rounded-md border border-dashed py-16 text-center text-sm text-muted-foreground"
            >
              <Users class="h-5 w-5" />
              <span>请选择一个班级查看成员</span>
            </div>

            <template v-else>
              <div class="flex flex-wrap items-center justify-between gap-2">
                <div class="min-w-0">
                  <h2 class="truncate text-sm font-medium">{{ selectedClassroom.name }} · 成员</h2>
                  <p class="text-xs text-muted-foreground">
                    <template v-if="canManage">已选 {{ selectedIds.size }} / {{ students.length }} 名学生</template>
                    <template v-else>{{ currentMembers.length }} 名成员</template>
                  </p>
                </div>
                <div v-if="canManage" class="flex items-center gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    :disabled="!dirty || savingMembers"
                    @click="resetSelection"
                  >
                    重置
                  </Button>
                  <Button size="sm" :disabled="!dirty || savingMembers" @click="saveMembers">
                    <Loader2 v-if="savingMembers" class="mr-2 h-4 w-4 animate-spin" />
                    <Save v-else class="mr-2 h-4 w-4" />
                    保存成员
                  </Button>
                </div>
              </div>

              <div v-if="loadingMembers" class="flex justify-center py-12">
                <Loader2 class="h-5 w-5 animate-spin text-muted-foreground" />
              </div>

              <div
                v-else-if="membersError"
                class="flex flex-col items-center gap-3 py-12 text-center text-sm text-muted-foreground"
              >
                <AlertTriangle class="h-5 w-5 text-amber-500" />
                <span>加载班级成员失败</span>
                <Button size="sm" variant="outline" @click="loadMembers(selectedClassroom.id)">重试</Button>
              </div>

              <!-- 可编辑：全部学生 checkbox 列表 -->
              <template v-else-if="canManage">
                <div class="relative">
                  <Search class="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                  <Input v-model="memberSearch" placeholder="搜索学生（学号或姓名）" class="pl-9" />
                </div>
                <div
                  v-if="students.length === 0"
                  class="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground"
                >
                  当前学科还没有学生，请先创建学生。
                </div>
                <div v-else class="max-h-[420px] overflow-auto rounded-md border">
                  <label
                    v-for="s in editorStudents"
                    :key="s.id"
                    class="flex cursor-pointer items-center gap-3 border-b px-3 py-2 text-sm last:border-b-0 hover:bg-accent"
                  >
                    <Checkbox
                      :model-value="selectedIds.has(s.id)"
                      @update:model-value="(v) => toggleStudent(s.id, v === true)"
                    />
                    <span class="w-24 shrink-0 truncate font-mono text-xs text-muted-foreground">{{ s.student_no }}</span>
                    <span class="min-w-0 flex-1 truncate">{{ s.name }}</span>
                  </label>
                  <div
                    v-if="editorStudents.length === 0"
                    class="px-3 py-6 text-center text-sm text-muted-foreground"
                  >
                    没有匹配的学生
                  </div>
                </div>
                <p v-if="studentsTruncated" class="text-xs text-muted-foreground">
                  当前仅支持从前 {{ students.length }} 名学生中选择成员（共 {{ studentsTotal }} 名）。
                </p>
              </template>

              <!-- 只读：当前成员列表 -->
              <template v-else>
                <div
                  v-if="currentMembers.length === 0"
                  class="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground"
                >
                  该班级还没有成员
                </div>
                <div v-else class="max-h-[420px] overflow-auto rounded-md border">
                  <div
                    v-for="s in currentMembers"
                    :key="s.id"
                    class="flex items-center gap-3 border-b px-3 py-2 text-sm last:border-b-0"
                  >
                    <span class="w-24 shrink-0 truncate font-mono text-xs text-muted-foreground">{{ s.student_no }}</span>
                    <span class="min-w-0 flex-1 truncate">{{ s.name }}</span>
                  </div>
                </div>
              </template>
            </template>
          </div>
        </div>

        <!-- 学生名册表 -->
        <div class="flex flex-col gap-2">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 class="text-sm font-medium">学生名册</h2>
              <p class="text-xs text-muted-foreground">共 {{ studentsTotal }} 名学生</p>
            </div>
            <div class="relative w-full sm:w-72">
              <Search class="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input v-model="studentSearch" placeholder="搜索学生（学号或姓名）" class="pl-9" />
            </div>
          </div>

          <div
            v-if="students.length === 0"
            class="flex flex-col items-center gap-2 rounded-md border border-dashed py-12 text-center text-sm text-muted-foreground"
          >
            <Users class="h-5 w-5" />
            <span>当前学科还没有学生</span>
            <Button v-if="canManage" size="sm" variant="outline" @click="openCreateStudent">
              <UserPlus class="mr-2 h-4 w-4" />
              创建学生
            </Button>
          </div>

          <div v-else class="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead class="w-40">学号</TableHead>
                  <TableHead>姓名</TableHead>
                  <TableHead class="text-right">当前选中班级</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow v-for="s in filteredStudents" :key="s.id">
                  <TableCell class="font-mono text-xs text-muted-foreground">{{ s.student_no }}</TableCell>
                  <TableCell>{{ s.name }}</TableCell>
                  <TableCell class="text-right text-xs text-muted-foreground">
                    <span v-if="selectedClassroom && baselineIds.has(s.id)">{{ classroomNameById.get(selectedClassroom.id) }}</span>
                    <span v-else>—</span>
                  </TableCell>
                </TableRow>
                <TableRow v-if="filteredStudents.length === 0">
                  <TableCell colspan="3" class="py-8 text-center text-sm text-muted-foreground">
                    没有匹配的学生
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </div>
          <p v-if="studentsTruncated" class="text-xs text-muted-foreground">
            当前仅显示前 {{ students.length }} 名学生（共 {{ studentsTotal }} 名）。
          </p>
        </div>
      </template>
    </div>

    <!-- 创建学生 -->
    <Dialog v-model:open="createStudentOpen">
      <DialogContent class="sm:max-w-[420px]">
        <DialogHeader>
          <DialogTitle>创建学生</DialogTitle>
          <DialogDescription>创建后可继续添加，学号在本学科内需唯一。</DialogDescription>
        </DialogHeader>
        <div class="space-y-4 py-2">
          <div class="space-y-2">
            <Label for="student-no">学号</Label>
            <Input id="student-no" v-model="studentForm.student_no" placeholder="例如：20240001" />
          </div>
          <div class="space-y-2">
            <Label for="student-name">姓名</Label>
            <Input
              id="student-name"
              v-model="studentForm.name"
              placeholder="学生姓名"
              @keyup.enter="submitCreateStudent"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="createStudentOpen = false">完成</Button>
          <Button :disabled="creatingStudent" @click="submitCreateStudent">
            <Loader2 v-if="creatingStudent" class="mr-2 h-4 w-4 animate-spin" />
            创建并继续
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- 创建班级 -->
    <Dialog v-model:open="createClassroomOpen">
      <DialogContent class="sm:max-w-[420px]">
        <DialogHeader>
          <DialogTitle>创建班级</DialogTitle>
          <DialogDescription>创建后将自动选中该班级以便编辑成员。</DialogDescription>
        </DialogHeader>
        <div class="space-y-4 py-2">
          <div class="space-y-2">
            <Label for="classroom-name">班级名称</Label>
            <Input
              id="classroom-name"
              v-model="classroomName"
              placeholder="例如：高三（1）班"
              @keyup.enter="submitCreateClassroom"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="createClassroomOpen = false">取消</Button>
          <Button :disabled="creatingClassroom" @click="submitCreateClassroom">
            <Loader2 v-if="creatingClassroom" class="mr-2 h-4 w-4 animate-spin" />
            创建
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
