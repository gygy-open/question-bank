<script setup lang="ts">
import { useAPI } from '~/composables/useAPI'
import { toast } from 'vue-sonner'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Avatar,
  AvatarFallback,
  AvatarImage,
} from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Loader2, Pencil, Trash2, Plus, TriangleAlert } from 'lucide-vue-next'
import type { User, Subject } from '~/types'

const { $api } = useNuxtApp()
const { data: users, refresh, status } = await useAPI<User[]>('/users')
const { data: subjects } = useAPI<Subject[]>('/subjects')

const isDialogOpen = ref(false)
const isDeleteConfirmOpen = ref(false)
const userToDelete = ref<User | null>(null)
const deleteConfirmationUsername = ref('')
const isEditing = ref(false)
const isLoading = ref(false)

const formData = reactive({
  id: 0,
  username: '',
  full_name: '',
  avatar_url: '',
  password: '',
  is_active: true,
  is_superuser: false,
  subject_id: null as number | null,
})

const resetForm = () => {
  formData.id = 0
  formData.username = ''
  formData.full_name = ''
  formData.avatar_url = ''
  formData.password = ''
  formData.is_active = true
  formData.is_superuser = false
  formData.subject_id = null
  isEditing.value = false
}

const openCreateDialog = () => {
  resetForm()
  isDialogOpen.value = true
}

const openEditDialog = (user: User) => {
  formData.id = user.id
  formData.username = user.username
  formData.full_name = user.full_name || ''
  formData.avatar_url = user.avatar_url || ''
  formData.password = '' // Password is not returned, and we only send if changing
  formData.is_active = user.is_active
  formData.is_superuser = user.is_superuser
  formData.subject_id = (user as any).subject_id || null
  isEditing.value = true
  isDialogOpen.value = true
}

const handleSubmit = async () => {
  // 验证
  if (!formData.username.trim()) {
    toast.error('用户名不能为空')
    return
  }
  if (!isEditing.value && !formData.password) {
    toast.error('创建用户时密码不能为空')
    return
  }
  if (!formData.full_name.trim()) {
    toast.error('姓名不能为空')
    return
  }
  if (!formData.subject_id) {
    toast.error('请选择负责科目')
    return
  }

  isLoading.value = true
  try {
    if (isEditing.value) {
      const payload: any = {
        username: formData.username,
        full_name: formData.full_name,
        avatar_url: formData.avatar_url,
        is_active: formData.is_active,
        is_superuser: formData.is_superuser,
        subject_id: formData.subject_id,
      }
      if (formData.password) {
        payload.password = formData.password
      }
      await $api(`/users/${formData.id}`, {
        method: 'PUT',
        body: payload,
      })
      toast.success('用户更新成功')
    } else {
      await $api('/users', {
        method: 'POST',
        body: {
          username: formData.username,
          full_name: formData.full_name,
          avatar_url: formData.avatar_url,
          password: formData.password,
          is_active: formData.is_active,
          is_superuser: formData.is_superuser,
          subject_id: formData.subject_id,
        },
      })
      toast.success('用户创建成功')
    }
    isDialogOpen.value = false
    refresh()
  } catch (error: any) {
    const detail = error.data?.detail || '操作失败'
    toast.error(detail)
  } finally {
    isLoading.value = false
  }
}

const openDeleteConfirm = (user: User) => {
  userToDelete.value = user
  deleteConfirmationUsername.value = ''
  isDeleteConfirmOpen.value = true
}

const confirmDelete = async () => {
  if (!userToDelete.value) return
  
  if (deleteConfirmationUsername.value !== userToDelete.value.username) {
    toast.error('用户名输入不匹配')
    return
  }

  isLoading.value = true
  try {
    await $api(`/users/${userToDelete.value.id}`, {
      method: 'DELETE',
    })
    toast.success('用户删除成功')
    refresh()
    isDeleteConfirmOpen.value = false
  } catch (error: any) {
    const detail = error.data?.detail || '删除失败'
    toast.error(detail)
  } finally {
    isLoading.value = false
    userToDelete.value = null
  }
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex justify-between items-center">
      <h2 class="text-lg font-medium">用户列表</h2>
      <Button @click="openCreateDialog">
        <Plus class="mr-2 h-4 w-4" />
        新增用户
      </Button>
    </div>

    <div class="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>ID</TableHead>
            <TableHead>头像</TableHead>
            <TableHead>用户名</TableHead>
            <TableHead>姓名</TableHead>
            <TableHead>负责科目</TableHead>
            <TableHead>状态</TableHead>
            <TableHead>角色</TableHead>
            <TableHead class="text-right">操作</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow v-if="status === 'pending'">
            <TableCell colspan="8" class="h-24 text-center">
              <Loader2 class="h-6 w-6 animate-spin mx-auto" />
            </TableCell>
          </TableRow>
          <TableRow v-else-if="users?.length === 0">
            <TableCell colspan="8" class="h-24 text-center">
              暂无用户
            </TableCell>
          </TableRow>
          <TableRow v-for="user in users" :key="user.id">
            <TableCell>{{ user.id }}</TableCell>
            <TableCell>
              <Avatar>
                <AvatarImage :src="user.avatar_url || ''" :alt="user.username" />
                <AvatarFallback>{{ user.username.slice(0, 2).toUpperCase() }}</AvatarFallback>
              </Avatar>
            </TableCell>
            <TableCell>{{ user.username }}</TableCell>
            <TableCell>{{ user.full_name }}</TableCell>
            <TableCell>
              <span v-if="(user as any).subject_id" class="text-blue-600">
                {{ subjects?.find(s => s.id === (user as any).subject_id)?.name || '未知' }}
              </span>
              <span v-else class="text-gray-400">未分配</span>
            </TableCell>
            <TableCell>
              <span :class="user.is_active ? 'text-green-600' : 'text-red-600'">
                {{ user.is_active ? '启用' : '禁用' }}
              </span>
            </TableCell>
            <TableCell>
              <span :class="user.is_superuser ? 'text-purple-600 font-medium' : 'text-gray-600'">
                {{ user.is_superuser ? '管理员' : '普通用户' }}
              </span>
            </TableCell>
            <TableCell class="text-right space-x-2">
              <Button variant="ghost" size="icon" @click="openEditDialog(user)">
                <Pencil class="h-4 w-4" />
              </Button>
              <Button variant="ghost" size="icon" class="text-red-600 hover:text-red-700 hover:bg-red-50" @click="openDeleteConfirm(user)">
                <Trash2 class="h-4 w-4" />
              </Button>
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>

    <Dialog :open="isDialogOpen" @update:open="isDialogOpen = $event">
      <DialogContent class="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>{{ isEditing ? '编辑用户' : '新增用户' }}</DialogTitle>
          <DialogDescription>
            {{ isEditing ? '修改用户信息，留空密码则不修改。' : '创建一个新的用户账号。' }}
          </DialogDescription>
        </DialogHeader>
        <div class="grid gap-4 py-4">
          <div class="grid grid-cols-4 items-center gap-4">
            <Label for="username" class="text-right">
              用户名 <span class="text-red-500">*</span>
            </Label>
            <Input
              id="username"
              v-model="formData.username"
              class="col-span-3"
              autocomplete="off"
              placeholder="必填"
            />
          </div>
          <div class="grid grid-cols-4 items-center gap-4">
            <Label for="full_name" class="text-right">
              姓名 <span class="text-red-500">*</span>
            </Label>
            <Input
              id="full_name"
              v-model="formData.full_name"
              class="col-span-3"
              placeholder="必填"
            />
          </div>
          <div class="grid grid-cols-4 items-center gap-4">
            <Label for="subject_id" class="text-right">
              负责科目 <span class="text-red-500">*</span>
            </Label>
            <Select
              :model-value="formData.subject_id?.toString() || '0'"
              @update:model-value="(v) => formData.subject_id = v === '0' ? null : parseInt(v)"
            >
              <SelectTrigger class="col-span-3">
                <SelectValue placeholder="选择科目" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="0">无</SelectItem>
                <SelectItem
                  v-for="subject in subjects"
                  :key="subject.id"
                  :value="subject.id.toString()"
                >
                  {{ subject.name }}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div class="grid grid-cols-4 items-center gap-4">
            <Label for="avatar_url" class="text-right">
              头像URL
            </Label>
            <Input
              id="avatar_url"
              v-model="formData.avatar_url"
              class="col-span-3"
              autocomplete="off"
            />
          </div>
          <div class="grid grid-cols-4 items-center gap-4">
            <Label for="password" class="text-right">
              密码 <span v-if="!isEditing" class="text-red-500">*</span>
            </Label>
            <Input
              id="password"
              type="password"
              v-model="formData.password"
              class="col-span-3"
              :placeholder="isEditing ? '留空保持不变' : '必填'"
              autocomplete="new-password"
            />
          </div>
          <div class="grid grid-cols-4 items-center gap-4">
            <Label class="text-right">状态</Label>
            <div class="col-span-3 flex items-center space-x-2">
              <input
                type="checkbox"
                id="is_active"
                v-model="formData.is_active"
                class="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary"
              />
              <Label for="is_active">启用</Label>
            </div>
          </div>
          <div class="grid grid-cols-4 items-center gap-4">
            <Label class="text-right">角色</Label>
            <div class="col-span-3 flex items-center space-x-2">
              <input
                type="checkbox"
                id="is_superuser"
                v-model="formData.is_superuser"
                class="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary"
              />
              <Label for="is_superuser">管理员</Label>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button type="submit" @click="handleSubmit" :disabled="isLoading">
            <Loader2 v-if="isLoading" class="mr-2 h-4 w-4 animate-spin" />
            保存
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Delete Confirmation Dialog -->
    <Dialog v-model:open="isDeleteConfirmOpen">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>确认删除用户？</DialogTitle>
          <DialogDescription class="py-4">
            <div class="flex items-start gap-4 p-4 bg-red-50 text-red-800 rounded-md mb-4">
              <TriangleAlert class="h-5 w-5 shrink-0 mt-0.5" />
              <div class="space-y-2">
                <p class="font-medium">警告：此操作不可逆！</p>
                <p class="text-sm">
                  删除后用户的行为数据会丢失，非必要不要删除，可以使用禁用功能。
                </p>
              </div>
            </div>
            <div class="space-y-2">
              <Label>请输入用户名 <span class="font-bold text-black">{{ userToDelete?.username }}</span> 以确认删除</Label>
              <Input v-model="deleteConfirmationUsername" placeholder="请输入用户名" />
            </div>
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" @click="isDeleteConfirmOpen = false">取消</Button>
          <Button 
            variant="destructive" 
            :disabled="isLoading || deleteConfirmationUsername !== userToDelete?.username" 
            @click="confirmDelete"
          >
            <Loader2 v-if="isLoading" class="mr-2 h-4 w-4 animate-spin" />
            确认删除
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
