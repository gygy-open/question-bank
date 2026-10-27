<script setup lang="ts">
import { getApiErrorCodeMessage } from '@/lib/apiErrors'
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
import { Loader2 } from '@lucide/vue'

const { t } = useI18n()

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
    toast.error(t('changePassword.currentRequired'))
    return
  }
  if (!formData.new_password) {
    toast.error(t('changePassword.newRequired'))
    return
  }
  if (formData.new_password !== formData.confirm_password) {
    toast.error(t('changePassword.mismatch'))
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
    toast.success(t('changePassword.success'))
    emit('update:open', false)
  } catch (error: any) {
    const detail = getApiErrorCodeMessage(error) || error.data?.detail || t('changePassword.failed')
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
        <DialogTitle>{{ t('changePassword.title') }}</DialogTitle>
        <DialogDescription>
          {{ t('changePassword.description') }}
        </DialogDescription>
      </DialogHeader>
      <div class="grid gap-4 py-4">
        <div class="grid grid-cols-4 items-center gap-4">
          <Label for="current_password" class="text-right">
            {{ t('changePassword.current') }}
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
            {{ t('changePassword.new') }}
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
            {{ t('changePassword.confirm') }}
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
          {{ t('common.save') }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
