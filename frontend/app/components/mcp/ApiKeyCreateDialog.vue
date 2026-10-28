<script setup lang="ts">
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import * as z from 'zod'
import { toast } from 'vue-sonner'
import { AlertTriangle, Check, Copy, Loader2 } from '@lucide/vue'
import { useClipboard } from '@vueuse/core'
import type { ApiKeyCreated } from '~/types/api-key'
import { apiErrorMessage } from '~/composables/useAIConfigApi'
import McpClientGuide from '~/components/mcp/McpClientGuide.vue'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Input } from '@/components/ui/input'

const NAME_MAX = 100

const props = defineProps<{ url: string }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ (e: 'created', key: ApiKeyCreated): void }>()

const { t } = useI18n()
const { $api } = useNuxtApp()

const created = ref<ApiKeyCreated | null>(null)
const submitting = ref(false)

const formSchema = computed(() => toTypedSchema(z.object({
  name: z.string()
    .trim()
    .min(1, t('settings.mcp.create.nameRequired'))
    .max(NAME_MAX, t('settings.mcp.create.nameMax', { max: NAME_MAX })),
})))

const form = useForm({ validationSchema: formSchema, initialValues: { name: '' } })

watch(open, (value) => {
  if (value) {
    created.value = null
    form.resetForm({ values: { name: '' } })
  } else {
    // 明文只在这个窗口里出现,关掉就丢弃
    created.value = null
  }
})

const onSubmit = form.handleSubmit(async (values) => {
  submitting.value = true
  try {
    const key = await $api<ApiKeyCreated>('/api-keys', { method: 'POST', body: { name: values.name } })
    created.value = key
    emit('created', key)
  } catch (e) {
    toast.error(t('common.operationFailed'), { description: apiErrorMessage(e) })
  } finally {
    submitting.value = false
  }
})

const { copy, copied, isSupported } = useClipboard({ copiedDuring: 1500 })
</script>

<template>
  <Dialog v-model:open="open">
    <DialogContent :class="created ? 'sm:max-w-2xl' : 'sm:max-w-md'">
      <template v-if="!created">
        <DialogHeader>
          <DialogTitle>{{ t('settings.mcp.create.title') }}</DialogTitle>
          <DialogDescription>{{ t('settings.mcp.create.description') }}</DialogDescription>
        </DialogHeader>
        <form class="space-y-4" @submit="onSubmit">
          <FormField v-slot="{ componentField }" name="name">
            <FormItem>
              <FormLabel>{{ t('settings.mcp.create.nameLabel') }}</FormLabel>
              <FormControl>
                <Input
                  type="text"
                  autocomplete="off"
                  :maxlength="NAME_MAX"
                  :placeholder="t('settings.mcp.create.namePlaceholder')"
                  v-bind="componentField"
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          </FormField>
          <DialogFooter>
            <Button type="button" variant="outline" @click="open = false">{{ t('common.cancel') }}</Button>
            <Button type="submit" :disabled="submitting">
              <Loader2 v-if="submitting" class="mr-2 h-4 w-4 animate-spin" />
              {{ t('settings.mcp.create.submit') }}
            </Button>
          </DialogFooter>
        </form>
      </template>

      <template v-else>
        <DialogHeader>
          <DialogTitle>{{ t('settings.mcp.create.createdTitle') }}</DialogTitle>
          <DialogDescription>{{ created.name }}</DialogDescription>
        </DialogHeader>
        <div class="min-w-0 space-y-4">
          <Alert variant="destructive">
            <AlertTriangle class="h-4 w-4" />
            <AlertDescription>{{ t('settings.mcp.create.createdWarning') }}</AlertDescription>
          </Alert>
          <div class="flex items-center gap-2">
            <code class="min-w-0 flex-1 break-all rounded-md bg-muted px-3 py-2 font-mono text-sm" data-testid="mcp-new-key">
              {{ created.key }}
            </code>
            <Button v-if="isSupported" size="icon" variant="outline" :title="t('common.copy')" @click="copy(created.key)">
              <Check v-if="copied" class="size-4 text-green-600" />
              <Copy v-else class="size-4" />
            </Button>
          </div>
          <McpClientGuide :url="props.url" :api-key="created.key" />
        </div>
        <DialogFooter>
          <Button @click="open = false">{{ t('settings.mcp.create.done') }}</Button>
        </DialogFooter>
      </template>
    </DialogContent>
  </Dialog>
</template>
