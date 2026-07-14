<script setup lang="ts">
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
import { Loader2 } from 'lucide-vue-next'

const props = defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
}>()

const { $api } = useNuxtApp()

const isLoading = ref(false)

const formData = reactive({
  current_password: '',
  new_password: '',
  confirm_password: '',
})

watch(() => props.open, (newVal) => {
  if (newVal) {
    formData.current_password = ''
    formData.new_password = ''
    formData.confirm_password = ''
  }
})

const handleSubmit = async () => {
  if (!formData.current_password) {
    toast.error('请输入当前密码')
    return
  }
  if (!formData.new_password) {
    toast.error('请输入新密码')
    return
  }
  if (formData.new_password !== formData.confirm_password) {
    toast.error('两次输入的密码不一致')
    return
  }

  isLoading.value = true
  try {
    await $api('/users/me/password', {
      method: 'POST',
      body: {
        current_password: formData.current_password,
        new_password: formData.new_password,
      },
    })
    toast.success('密码修改成功')
    emit('update:open', false)
  } catch (error: any) {
    const detail = error.data?.detail || '修改失败'
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
        <DialogTitle>修改密码</DialogTitle>
        <DialogDescription>
          请输入当前密码和新密码。
        </DialogDescription>
      </DialogHeader>
      <div class="grid gap-4 py-4">
        <div class="grid grid-cols-4 items-center gap-4">
          <Label for="current_password" class="text-right">
            当前密码
          </Label>
          <Input
            id="current_password"
            type="password"
            v-model="formData.current_password"
            class="col-span-3"
          />
        </div>
        <div class="grid grid-cols-4 items-center gap-4">
          <Label for="new_password" class="text-right">
            新密码
          </Label>
          <Input
            id="new_password"
            type="password"
            v-model="formData.new_password"
            class="col-span-3"
          />
        </div>
        <div class="grid grid-cols-4 items-center gap-4">
          <Label for="confirm_password" class="text-right">
            确认新密码
          </Label>
          <Input
            id="confirm_password"
            type="password"
            v-model="formData.confirm_password"
            class="col-span-3"
          />
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
</template>
