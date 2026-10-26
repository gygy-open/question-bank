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
import { Badge } from '@/components/ui/badge'
import ClearableInput from '~/components/ClearableInput.vue'
import { Loader2, Pencil, Trash2, Plus, TriangleAlert, KeyRound, Upload, Eye, EyeOff } from '@lucide/vue'
import UserImportDialog from '~/components/manager/UserImportDialog.vue'
import type { User } from '~/types'

const { t } = useI18n()
const { $api } = useNuxtApp()
const { data: users, refresh, status } = await useAPI<User[]>('/users')

const searchQuery = ref('')
const roleFilter = ref('all')
const isImportOpen = ref(false)

const filteredUsers = computed(() => {
  const keyword = searchQuery.value.trim().toLowerCase()
  return (users.value || []).filter((user) => {
    if (roleFilter.value === 'admin' && !user.is_superuser) return false
    if (roleFilter.value === 'normal' && user.is_superuser) return false
    if (!keyword) return true
    return user.username.toLowerCase().includes(keyword) || (user.full_name || '').toLowerCase().includes(keyword)
  })
})

const isDialogOpen = ref(false)
const isDeleteConfirmOpen = ref(false)
const userToDelete = ref<User | null>(null)
const deleteConfirmationUsername = ref('')
const isEditing = ref(false)
const isLoading = ref(false)

const isResetPasswordOpen = ref(false)
const userToReset = ref<User | null>(null)
const newPassword = ref('')
const confirmPassword = ref('')

const showPassword = ref(false)
const showNewPassword = ref(false)
const showConfirmPassword = ref(false)

const formData = reactive({
  id: 0,
  username: '',
  full_name: '',
  avatar_url: '',
  password: '',
  is_active: true,
  is_superuser: false,
})

const resetForm = () => {
  formData.id = 0
  formData.username = ''
  formData.full_name = ''
  formData.avatar_url = ''
  formData.password = ''
  formData.is_active = true
  formData.is_superuser = false
  isEditing.value = false
}

const openCreateDialog = () => {
  resetForm()
  showPassword.value = false
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
  isEditing.value = true
  isDialogOpen.value = true
}

const handleSubmit = async () => {
  // 验证
  if (!formData.username.trim()) {
    toast.error(t('users.validation.usernameRequired'))
    return
  }
  if (!isEditing.value && !formData.password) {
    toast.error(t('users.validation.passwordRequired'))
    return
  }
  if (!formData.full_name.trim()) {
    toast.error(t('users.validation.fullNameRequired'))
    return
  }

  isLoading.value = true
  try {
    if (isEditing.value) {
      const payload = {
        username: formData.username,
        full_name: formData.full_name,
        avatar_url: formData.avatar_url,
        is_active: formData.is_active,
        is_superuser: formData.is_superuser,
      }
      await $api(`/users/${formData.id}`, {
        method: 'PUT',
        body: payload,
      })
      toast.success(t('users.toast.updated'))
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
        },
      })
      toast.success(t('users.toast.created'))
    }
    isDialogOpen.value = false
    refresh()
  } catch (error: any) {
    const detail = error.data?.detail || t('common.operationFailed')
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
    toast.error(t('users.toast.usernameMismatch'))
    return
  }

  isLoading.value = true
  try {
    await $api(`/users/${userToDelete.value.id}`, {
      method: 'DELETE',
    })
    toast.success(t('users.toast.deleted'))
    refresh()
    isDeleteConfirmOpen.value = false
  } catch (error: any) {
    const detail = error.data?.detail || t('common.deleteFailed')
    toast.error(detail)
  } finally {
    isLoading.value = false
    userToDelete.value = null
  }
}

const openResetPasswordDialog = (user: User) => {
  userToReset.value = user
  newPassword.value = ''
  confirmPassword.value = ''
  showNewPassword.value = false
  showConfirmPassword.value = false
  isResetPasswordOpen.value = true
}

const confirmResetPassword = async () => {
  if (!userToReset.value) return
  if (!newPassword.value) {
    toast.error(t('users.validation.newPasswordRequired'))
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    toast.error(t('users.validation.passwordMismatch'))
    return
  }

  isLoading.value = true
  try {
    await $api(`/users/${userToReset.value.id}`, {
      method: 'PUT',
      body: { password: newPassword.value },
    })
    toast.success(t('users.toast.passwordReset'))
    isResetPasswordOpen.value = false
  } catch (error: any) {
    const detail = error.data?.detail || t('users.toast.resetFailed')
    toast.error(detail)
  } finally {
    isLoading.value = false
    userToReset.value = null
  }
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="flex flex-1 items-center gap-2">
        <ClearableInput v-model="searchQuery" :placeholder="t('users.searchPlaceholder')" class="max-w-xs" />
        <Select v-model="roleFilter">
          <SelectTrigger class="w-32">
            <SelectValue :placeholder="t('users.allRoles')" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{{ t('users.allRoles') }}</SelectItem>
            <SelectItem value="admin">{{ t('users.roleAdmin') }}</SelectItem>
            <SelectItem value="normal">{{ t('users.roleNormal') }}</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div class="flex items-center gap-2">
        <Button variant="outline" @click="isImportOpen = true">
          <Upload class="mr-2 h-4 w-4" />
          {{ t('users.batchImport') }}
        </Button>
        <Button @click="openCreateDialog">
          <Plus class="mr-2 h-4 w-4" />
          {{ t('users.create') }}
        </Button>
      </div>
    </div>

    <UserImportDialog v-model:open="isImportOpen" @imported="refresh" />
    <div class="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>ID</TableHead>
            <TableHead>{{ t('users.columns.avatar') }}</TableHead>
            <TableHead>{{ t('users.columns.username') }}</TableHead>
            <TableHead>{{ t('users.columns.fullName') }}</TableHead>
            <TableHead>{{ t('users.columns.status') }}</TableHead>
            <TableHead>{{ t('users.columns.role') }}</TableHead>
            <TableHead class="text-right">{{ t('common.actions') }}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow v-if="status === 'pending'">
            <TableCell colspan="7" class="h-24 text-center">
              <Loader2 class="h-6 w-6 animate-spin mx-auto" />
            </TableCell>
          </TableRow>
          <TableRow v-else-if="users?.length === 0">
            <TableCell colspan="7" class="h-24 text-center">
              {{ t('users.empty') }}
            </TableCell>
          </TableRow>
          <TableRow v-else-if="filteredUsers.length === 0">
            <TableCell colspan="7" class="h-24 text-center text-muted-foreground">
              {{ t('users.noMatch') }}
            </TableCell>
          </TableRow>
          <TableRow v-for="user in filteredUsers" :key="user.id">
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
              <Badge v-if="user.is_active" variant="outline" class="border-primary/30 bg-primary/5 text-primary">{{ t('users.active') }}</Badge>
              <Badge v-else variant="outline" class="text-muted-foreground">{{ t('users.disabled') }}</Badge>
            </TableCell>
            <TableCell>
              <Badge :variant="user.is_superuser ? 'default' : 'secondary'">
                {{ user.is_superuser ? t('users.roleAdmin') : t('users.roleNormal') }}
              </Badge>
            </TableCell>
            <TableCell class="text-right space-x-2">
              <Button variant="ghost" size="icon" :title="t('common.edit')" :aria-label="t('users.editUser')" @click="openEditDialog(user)">
                <Pencil class="h-4 w-4" />
              </Button>
              <Button variant="ghost" size="icon" :title="t('users.resetPassword')" :aria-label="t('users.resetPassword')" @click="openResetPasswordDialog(user)">
                <KeyRound class="h-4 w-4" />
              </Button>
              <Button variant="ghost" size="icon" :title="t('common.delete')" :aria-label="t('users.deleteUser')" class="text-destructive hover:text-destructive hover:bg-destructive/10" @click="openDeleteConfirm(user)">
                <Trash2 class="h-4 w-4" />
              </Button>
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>
    <p v-if="filteredUsers.length" class="text-sm text-muted-foreground">{{ t('users.total', { count: filteredUsers.length }) }}</p>

    <Dialog :open="isDialogOpen" @update:open="isDialogOpen = $event">
      <DialogContent class="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>{{ isEditing ? t('users.editUser') : t('users.create') }}</DialogTitle>
          <DialogDescription>
            {{ isEditing ? t('users.dialog.editDescription') : t('users.dialog.createDescription') }}
          </DialogDescription>
        </DialogHeader>
        <div class="grid gap-4 py-4">
          <div class="grid grid-cols-4 items-center gap-4">
            <Label for="username" class="text-right">
              {{ t('users.columns.username') }} <span class="text-red-500">*</span>
            </Label>
            <Input
              id="username"
              v-model="formData.username"
              class="col-span-3"
              autocomplete="off"
              :placeholder="t('users.required')"
            />
          </div>
          <div class="grid grid-cols-4 items-center gap-4">
            <Label for="full_name" class="text-right">
              {{ t('users.columns.fullName') }} <span class="text-red-500">*</span>
            </Label>
            <Input
              id="full_name"
              v-model="formData.full_name"
              class="col-span-3"
              :placeholder="t('users.required')"
            />
          </div>
          <div class="grid grid-cols-4 items-center gap-4">
            <Label for="avatar_url" class="text-right">
              {{ t('users.avatarUrl') }}
            </Label>
            <Input
              id="avatar_url"
              v-model="formData.avatar_url"
              class="col-span-3"
              autocomplete="off"
            />
          </div>
          <div v-if="!isEditing" class="grid grid-cols-4 items-center gap-4">
            <Label for="password" class="text-right">
              {{ t('users.password') }} <span class="text-red-500">*</span>
            </Label>
            <div class="col-span-3 relative">
              <Input
                id="password"
                :type="showPassword ? 'text' : 'password'"
                v-model="formData.password"
                class="pr-10"
                :placeholder="t('users.required')"
                autocomplete="new-password"
              />
              <button
                type="button"
                class="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                :aria-label="showPassword ? t('users.hidePassword') : t('users.showPassword')"
                @click="showPassword = !showPassword"
              >
                <EyeOff v-if="showPassword" class="h-4 w-4" />
                <Eye v-else class="h-4 w-4" />
              </button>
            </div>
          </div>
          <div class="grid grid-cols-4 items-center gap-4">
            <Label class="text-right">{{ t('users.columns.status') }}</Label>
            <div class="col-span-3 flex items-center space-x-2">
              <input
                type="checkbox"
                id="is_active"
                v-model="formData.is_active"
                class="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary"
              />
              <Label for="is_active">{{ t('users.active') }}</Label>
            </div>
          </div>
          <div class="grid grid-cols-4 items-center gap-4">
            <Label class="text-right">{{ t('users.columns.role') }}</Label>
            <div class="col-span-3 flex items-center space-x-2">
              <input
                type="checkbox"
                id="is_superuser"
                v-model="formData.is_superuser"
                class="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary"
              />
              <Label for="is_superuser">{{ t('users.roleAdmin') }}</Label>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button type="submit" @click="handleSubmit" :disabled="isLoading">
            <Loader2 v-if="isLoading" class="mr-2 h-4 w-4 animate-spin" />
            {{ t('common.save') }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Delete Confirmation Dialog -->
    <Dialog v-model:open="isDeleteConfirmOpen">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{{ t('users.delete.title') }}</DialogTitle>
          <DialogDescription class="py-4">
            <div class="flex items-start gap-4 p-4 bg-destructive/10 text-destructive rounded-md mb-4">
              <TriangleAlert class="h-5 w-5 shrink-0 mt-0.5" />
              <div class="space-y-2">
                <p class="font-medium">{{ t('users.delete.warning') }}</p>
                <p class="text-sm">
                  {{ t('users.delete.warningDescription') }}
                </p>
              </div>
            </div>
            <div class="space-y-2">
              <Label><i18n-t scope="global" keypath="users.delete.confirmLabel" tag="span"><template #username><span class="font-bold text-foreground">{{ userToDelete?.username }}</span></template></i18n-t></Label>
              <Input v-model="deleteConfirmationUsername" :placeholder="t('users.delete.inputPlaceholder')" />
            </div>
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" @click="isDeleteConfirmOpen = false">{{ t('common.cancel') }}</Button>
          <Button 
            variant="destructive" 
            :disabled="isLoading || deleteConfirmationUsername !== userToDelete?.username" 
            @click="confirmDelete"
          >
            <Loader2 v-if="isLoading" class="mr-2 h-4 w-4 animate-spin" />
            {{ t('common.confirmDelete') }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Reset Password Dialog -->
    <Dialog v-model:open="isResetPasswordOpen">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{{ t('users.resetPassword') }}</DialogTitle>
          <DialogDescription>
            <i18n-t scope="global" keypath="users.reset.description" tag="span"><template #username><span class="font-bold text-foreground">{{ userToReset?.username }}</span></template></i18n-t>
          </DialogDescription>
        </DialogHeader>
        <div class="grid gap-4 py-2">
          <div class="grid grid-cols-4 items-center gap-4">
            <Label for="new_password" class="text-right">
              {{ t('users.reset.newPassword') }} <span class="text-red-500">*</span>
            </Label>
            <div class="col-span-3 relative">
              <Input
                id="new_password"
                :type="showNewPassword ? 'text' : 'password'"
                v-model="newPassword"
                class="pr-10"
                :placeholder="t('users.required')"
                autocomplete="new-password"
              />
              <button
                type="button"
                class="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                :aria-label="showNewPassword ? t('users.hidePassword') : t('users.showPassword')"
                @click="showNewPassword = !showNewPassword"
              >
                <EyeOff v-if="showNewPassword" class="h-4 w-4" />
                <Eye v-else class="h-4 w-4" />
              </button>
            </div>
          </div>
          <div class="grid grid-cols-4 items-center gap-4">
            <Label for="confirm_password" class="text-right">
              {{ t('users.reset.confirmPassword') }} <span class="text-red-500">*</span>
            </Label>
            <div class="col-span-3 relative">
              <Input
                id="confirm_password"
                :type="showConfirmPassword ? 'text' : 'password'"
                v-model="confirmPassword"
                class="pr-10"
                :placeholder="t('users.required')"
                autocomplete="new-password"
              />
              <button
                type="button"
                class="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                :aria-label="showConfirmPassword ? t('users.hidePassword') : t('users.showPassword')"
                @click="showConfirmPassword = !showConfirmPassword"
              >
                <EyeOff v-if="showConfirmPassword" class="h-4 w-4" />
                <Eye v-else class="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="isResetPasswordOpen = false">{{ t('common.cancel') }}</Button>
          <Button :disabled="isLoading" @click="confirmResetPassword">
            <Loader2 v-if="isLoading" class="mr-2 h-4 w-4 animate-spin" />
            {{ t('users.reset.confirm') }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
