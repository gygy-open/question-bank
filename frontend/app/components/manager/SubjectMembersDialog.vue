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

const { t } = useI18n()
const { $api } = useNuxtApp()

const members = ref<SubjectMember[]>([])
const allUsers = ref<User[]>([])
const loading = ref(false)
const addUserId = ref<string>('')
const addRole = ref<string>('viewer')

const ROLE_LABEL_KEYS: Record<string, string> = {
  viewer: 'subjectMembers.roles.viewer',
  editor: 'subjectMembers.roles.editor',
  manager: 'subjectMembers.roles.manager',
}
const roleOptions = computed(() =>
  Object.entries(ROLE_LABEL_KEYS).map(([value, key]) => ({ value, label: t(key) })),
)

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
    toast.success(t('subjectMembers.roleUpdated'))
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
    toast.success(t('subjectMembers.removed'))
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
        <DialogTitle>{{ t('subjectMembers.title', { name: subject?.name ?? '' }) }}</DialogTitle>
        <DialogDescription>
          {{ t('subjectMembers.description') }}
        </DialogDescription>
      </DialogHeader>

      <!-- 添加成员 -->
      <div class="flex items-end gap-2">
        <div class="flex-1 space-y-1">
          <label class="text-xs text-muted-foreground">{{ t('subjectMembers.selectTeacher') }}</label>
          <Select v-model="addUserId">
            <SelectTrigger><SelectValue :placeholder="t('subjectMembers.selectTeacher')" /></SelectTrigger>
            <SelectContent>
              <SelectItem v-for="u in assignableUsers" :key="u.id" :value="String(u.id)">
                {{ t('subjectMembers.userDisplay', { name: u.full_name || u.username, username: u.username }) }}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div class="w-40 space-y-1">
          <label class="text-xs text-muted-foreground">{{ t('subjectMembers.role') }}</label>
          <Select v-model="addRole">
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem v-for="opt in roleOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <Button :disabled="!addUserId" @click="addMember">{{ t('common.add') }}</Button>
      </div>

      <!-- 成员列表 -->
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{{ t('subjectMembers.teacher') }}</TableHead>
            <TableHead class="w-40">{{ t('subjectMembers.role') }}</TableHead>
            <TableHead class="w-16 text-right">{{ t('common.actions') }}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow v-if="members.length === 0">
            <TableCell colspan="3" class="text-center text-muted-foreground">
              {{ loading ? t('common.loading') : t('subjectMembers.empty') }}
            </TableCell>
          </TableRow>
          <TableRow v-for="m in members" :key="m.id">
            <TableCell>{{ t('subjectMembers.userDisplay', { name: m.full_name || m.username, username: m.username }) }}</TableCell>
            <TableCell>
              <Select :model-value="m.role" @update:model-value="(v) => setRole(m.user_id, String(v))">
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem v-for="opt in roleOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</SelectItem>
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
