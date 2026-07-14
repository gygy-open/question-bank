<script setup lang="ts">
import { useAuth } from '~/composables/useAuth'
import { toast } from 'vue-sonner'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Loader2, Upload } from 'lucide-vue-next'

const props = defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
}>()

const { user, fetchUser } = useAuth()
const { $api } = useNuxtApp()

const isLoading = ref(false)
const isUploading = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

const formData = reactive({
  full_name: '',
  avatar_url: '',
})

watch(() => props.open, (newVal) => {
  if (newVal && user.value) {
    formData.full_name = user.value.full_name || ''
    formData.avatar_url = user.value.avatar_url || ''
  }
})

const handleFileSelect = async (event: Event) => {
  const input = event.target as HTMLInputElement
  if (!input.files?.length) return

  const file = input.files[0]
  if (!file.type.startsWith('image/')) {
    toast.error('请选择图片文件')
    return
  }

  isUploading.value = true
  try {
    const uploadFormData = new FormData()
    uploadFormData.append('file', file)

    const res = await $api<{ url: string }>('/upload/image', {
      method: 'POST',
      body: uploadFormData,
    })

    formData.avatar_url = res.url
    toast.success('头像上传成功')
  } catch (error: any) {
    const detail = error.data?.detail || '上传失败'
    toast.error(detail)
  } finally {
    isUploading.value = false
    // Reset input so same file can be selected again if needed
    input.value = ''
  }
}

const triggerFileInput = () => {
  fileInput.value?.click()
}

const handleSubmit = async () => {
  isLoading.value = true
  try {
    await $api('/users/me', {
      method: 'PUT',
      body: {
        full_name: formData.full_name,
        avatar_url: formData.avatar_url,
      },
    })
    await fetchUser()
    toast.success('个人信息更新成功')
    emit('update:open', false)
  } catch (error: any) {
    const detail = error.data?.detail || '更新失败'
    toast.error(detail)
  } finally {
    isLoading.value = false
  }
}
</script>

<template>
  <Dialog :open="open" @update:open="$emit('update:open', $event)">
    <DialogContent class="sm:max-w-[425px]">
      <DialogHeader>
        <DialogTitle>个人资料</DialogTitle>
        <DialogDescription>
          修改您的个人信息。
        </DialogDescription>
      </DialogHeader>
      <div class="grid gap-4 py-4">
        <div class="flex flex-col items-center gap-4">
          <Avatar class="h-24 w-24">
            <AvatarImage :src="formData.avatar_url" />
            <AvatarFallback>{{ user?.username?.slice(0, 2).toUpperCase() }}</AvatarFallback>
          </Avatar>
          <div class="flex items-center gap-2">
            <Button variant="outline" size="sm" @click="triggerFileInput" :disabled="isUploading">
              <Loader2 v-if="isUploading" class="mr-2 h-4 w-4 animate-spin" />
              <Upload v-else class="mr-2 h-4 w-4" />
              上传头像
            </Button>
            <input
              ref="fileInput"
              type="file"
              accept="image/*"
              class="hidden"
              @change="handleFileSelect"
            />
          </div>
        </div>
        <div class="grid grid-cols-4 items-center gap-4">
          <Label for="username" class="text-right">
            用户名
          </Label>
          <Input
            id="username"
            :model-value="user?.username"
            class="col-span-3"
            disabled
          />
        </div>
        <div class="grid grid-cols-4 items-center gap-4">
          <Label for="full_name" class="text-right">
            姓名
          </Label>
          <Input
            id="full_name"
            v-model="formData.full_name"
            class="col-span-3"
            disabled
          />
        </div>
      </div>
      <DialogFooter>
        <Button type="submit" @click="handleSubmit" :disabled="isLoading || isUploading">
          <Loader2 v-if="isLoading" class="mr-2 h-4 w-4 animate-spin" />
          保存
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
