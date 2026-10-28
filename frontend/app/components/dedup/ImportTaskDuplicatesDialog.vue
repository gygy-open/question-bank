<script setup lang="ts">
import { Loader2, Trash2 } from '@lucide/vue'
import { toast } from 'vue-sonner'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import DuplicateCandidateList from '@/components/dedup/DuplicateCandidateList.vue'
import type { DuplicateCandidate } from '@/lib/questionDedup'
import { apiErrorMessage } from '~/composables/useAIConfigApi'

const props = defineProps<{
  /** 新题 id → 题库中的候选(来自导入任务 result_summary.duplicates) */
  duplicates: Record<string, DuplicateCandidate[]>
}>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ (e: 'deleted', ids: number[]): void }>()

const { t } = useI18n()
const { $api } = useNuxtApp()

const loading = ref(false)
const deleting = ref(false)
const existingIds = ref<number[]>([])
const selected = ref<number[]>([])

const entries = computed(() =>
  existingIds.value.map((id) => ({ id, candidates: props.duplicates[String(id)] ?? [] })),
)

const load = async () => {
  const ids = Object.keys(props.duplicates).map(Number)
  selected.value = []
  if (!ids.length) {
    existingIds.value = []
    return
  }
  loading.value = true
  try {
    // 只展示仍存在的新题(之前已删掉的不再出现)
    const page = await $api<{ items: { id: number }[] }>('/questions', { query: { ids, size: ids.length } })
    const alive = new Set(page.items.map((q) => q.id))
    existingIds.value = ids.filter((id) => alive.has(id))
  } catch (e) {
    toast.error(t('common.operationFailed'), { description: apiErrorMessage(e) })
    existingIds.value = ids
  } finally {
    loading.value = false
  }
}

watch(open, (value) => { if (value) load() })

const toggle = (id: number, checked: boolean | 'indeterminate') => {
  selected.value = checked === true
    ? [...selected.value, id]
    : selected.value.filter((x) => x !== id)
}

const removeSelected = async () => {
  if (!selected.value.length) return
  deleting.value = true
  try {
    const ids = [...selected.value]
    await $api('/questions/batch-delete', { method: 'POST', body: { ids } })
    existingIds.value = existingIds.value.filter((id) => !ids.includes(id))
    selected.value = []
    toast.success(t('questionDedup.task.deleted', { count: ids.length }))
    emit('deleted', ids)
  } catch (e) {
    toast.error(t('common.deleteFailed'), { description: apiErrorMessage(e) })
  } finally {
    deleting.value = false
  }
}
</script>

<template>
  <Dialog v-model:open="open">
    <DialogContent class="sm:max-w-3xl">
      <DialogHeader>
        <DialogTitle>{{ t('questionDedup.task.title') }}</DialogTitle>
        <DialogDescription>{{ t('questionDedup.task.description') }}</DialogDescription>
      </DialogHeader>
      <div class="max-h-[60vh] space-y-4 overflow-y-auto">
        <div v-if="loading" class="flex justify-center py-8">
          <Loader2 class="size-5 animate-spin text-muted-foreground" />
        </div>
        <p v-else-if="!entries.length" class="py-8 text-center text-sm text-muted-foreground">
          {{ t('questionDedup.task.empty') }}
        </p>
        <section v-for="entry in entries" v-else :key="entry.id" class="space-y-2 rounded-lg border p-3">
          <label class="flex items-center gap-2 text-sm font-medium">
            <Checkbox
              :model-value="selected.includes(entry.id)"
              @update:model-value="(checked) => toggle(entry.id, checked)"
            />
            {{ t('questionDedup.task.newQuestion') }}
            <NuxtLink :to="{ path: '/questions', query: { id: entry.id } }" target="_blank" class="text-primary hover:underline">
              #{{ entry.id }}
            </NuxtLink>
          </label>
          <DuplicateCandidateList :candidates="entry.candidates" />
        </section>
      </div>
      <DialogFooter>
        <Button variant="outline" @click="open = false">{{ t('common.close') }}</Button>
        <Button variant="destructive" :disabled="!selected.length || deleting" @click="removeSelected">
          <Loader2 v-if="deleting" class="mr-2 size-4 animate-spin" />
          <Trash2 v-else class="mr-2 size-4" />
          {{ t('questionDedup.task.deleteSelected', { count: selected.length }) }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
