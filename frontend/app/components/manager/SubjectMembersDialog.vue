<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { toast } from 'vue-sonner'
import type { Subject, User } from '~/types'
import {
  Dialog,
  DialogContent,
  DialogDescription,
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
import { Button } from '@/components/ui/button'
import { Trash2 } from '@lucide/vue'

interface SubjectMember {
  id: number
  user_id: number
  subject_id: number
  role: string
  username?: string
  full_name?: string
}

const props = defineProps<{
  open: boolean
  subject: Subject | null
}>()

const emit = defineEmits<{ (e: 'update:open', v: boolean): void }>()

const { $api } = useNuxtApp()

const members = ref<SubjectMember[]>([])
const allUsers = ref<User[]>([])
const loading = ref(false)
const addUserId = ref<string>('')
const addRole = ref<string>('viewer')

const ROLE_LABELS: Record<string, string> = {
  viewer: '只读',
  editor: '可编辑',
  manager: '学科负责人',
}

const memberUserIds = computed(() => new Set(members.value.map((m) => m.user_id)))
const assignableUsers = computed(() =>
  allUsers.value.filter((u) => !memberUserIds.value.has(u.id)),
)

const load = async () => {
  if (!props.subject) return
  loading.value = true
  try {
    const [m, u] = await Promise.all([
      $api<SubjectMember[]>(`/subjects/${props.subject.id}/members`),
      $api<User[]>('/users'),
    ])
    members.value = m
    allUsers.value = u
  } catch {
    // 403 等错误由全局插件提示
  } finally {
    loading.value = false
  }
}

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) {
      addUserId.value = ''
      addRole.value = 'viewer'
      load()
    }
  },
)

const setRole = async (userId: number, role: string) => {
  if (!props.subject) return
  try {
    await $api(`/subjects/${props.subject.id}/members/${userId}`, {
      method: 'PUT',
      body: { role },
    })
    toast.success('已更新成员角色')
    await load()
  } catch {
    // 全局提示
  }
}

const addMember = async () => {
  if (!props.subject || !addUserId.value) return
  await setRole(Number(addUserId.value), addRole.value)
  addUserId.value = ''
  addRole.value = 'viewer'
}

const removeMember = async (userId: number) => {
  if (!props.subject) return
  try {
    await $api(`/subjects/${props.subject.id}/members/${userId}`, { method: 'DELETE' })
    toast.success('已移除成员')
    await load()
  } catch {
    // 全局提示
  }
}
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogContent class="max-w-2xl">
      <DialogHeader>
        <DialogTitle>成员管理 · {{ subject?.name }}</DialogTitle>
        <DialogDescription>
          为老师授予本学科的角色：只读、可编辑或学科负责人。未在此的老师看不到本学科。
        </DialogDescription>
      </DialogHeader>

      <!-- 添加成员 -->
      <div class="flex items-end gap-2">
        <div class="flex-1 space-y-1">
          <label class="text-xs text-muted-foreground">选择老师</label>
          <Select v-model="addUserId">
            <SelectTrigger><SelectValue placeholder="选择老师" /></SelectTrigger>
            <SelectContent>
              <SelectItem v-for="u in assignableUsers" :key="u.id" :value="String(u.id)">
                {{ u.full_name || u.username }}（{{ u.username }}）
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div class="w-40 space-y-1">
          <label class="text-xs text-muted-foreground">角色</label>
          <Select v-model="addRole">
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="viewer">只读</SelectItem>
              <SelectItem value="editor">可编辑</SelectItem>
              <SelectItem value="manager">学科负责人</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <Button :disabled="!addUserId" @click="addMember">添加</Button>
      </div>

      <!-- 成员列表 -->
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>老师</TableHead>
            <TableHead class="w-40">角色</TableHead>
            <TableHead class="w-16 text-right">操作</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow v-if="members.length === 0">
            <TableCell colspan="3" class="text-center text-muted-foreground">
              {{ loading ? '加载中…' : '暂无成员' }}
            </TableCell>
          </TableRow>
          <TableRow v-for="m in members" :key="m.id">
            <TableCell>{{ m.full_name || m.username }}（{{ m.username }}）</TableCell>
            <TableCell>
              <Select :model-value="m.role" @update:model-value="(v) => setRole(m.user_id, String(v))">
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="viewer">只读</SelectItem>
                  <SelectItem value="editor">可编辑</SelectItem>
                  <SelectItem value="manager">学科负责人</SelectItem>
                </SelectContent>
              </Select>
            </TableCell>
            <TableCell class="text-right">
              <Button variant="ghost" size="icon" class="text-destructive" @click="removeMember(m.user_id)">
                <Trash2 class="w-4 h-4" />
              </Button>
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </DialogContent>
  </Dialog>
</template>
