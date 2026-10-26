<script setup lang="ts">
import { ref, watch } from 'vue'
import { ChevronLeft, ChevronRight, Layers3, Loader2, Lock, Plus, Search } from '@lucide/vue'
import RichContent from '@/components/rich-editor/RichContent.vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import type { StimulusListItem } from '@/types'

const props = defineProps<{
  open: boolean
  subjectId: number | null | undefined
  questionVisibility: 'public' | 'private'
}>()
const emit = defineEmits<{
  'update:open': [value: boolean]
  select: [stimulusId: number | null]
}>()
const { t } = useI18n()
const { listStimuli } = useStimuli()
const keyword = ref('')
const page = ref(1)
const pages = ref(0)
const results = ref<StimulusListItem[]>([])
const loading = ref(false)
let debounce: ReturnType<typeof setTimeout> | undefined

const load = async () => {
  if (!props.subjectId) return
  loading.value = true
  try {
    const response = await listStimuli(props.subjectId, { page: page.value, size: 8, keyword: keyword.value.trim() || undefined })
    results.value = response.items
    pages.value = response.pages
  } finally {
    loading.value = false
  }
}
watch(() => props.open, (open) => {
  if (!open) return
  keyword.value = ''
  page.value = 1
  void load()
})
watch(keyword, () => { clearTimeout(debounce); debounce = setTimeout(() => { page.value = 1; void load() }, 250) })
watch(page, load)

const isIncompatible = (stimulus: StimulusListItem) =>
  stimulus.visibility === 'private' && props.questionVisibility === 'public'
const choose = (stimulusId: number | null) => {
  emit('select', stimulusId)
  emit('update:open', false)
}
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogContent class="max-w-2xl">
      <DialogHeader>
        <DialogTitle>{{ t('stimuli.targetPicker.title') }}</DialogTitle>
        <DialogDescription>{{ t('stimuli.targetPicker.description') }}</DialogDescription>
      </DialogHeader>
      <button type="button" class="flex w-full items-center gap-3 border border-dashed p-3 text-left hover:bg-muted/50" @click="choose(null)">
        <Plus class="size-4 shrink-0 text-muted-foreground" />
        <div>
          <div class="text-sm font-medium">{{ t('materials.create') }}</div>
          <div class="text-xs text-muted-foreground">{{ t('stimuli.targetPicker.createHint') }}</div>
        </div>
      </button>
      <div class="relative">
        <Search class="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input v-model="keyword" class="pl-9" :placeholder="t('stimuli.targetPicker.searchPlaceholder')" />
      </div>
      <div v-if="loading" class="flex h-72 items-center justify-center"><Loader2 class="size-6 animate-spin" /></div>
      <div v-else class="h-72 space-y-2 overflow-y-auto">
        <button
          v-for="stimulus in results"
          :key="stimulus.id"
          type="button"
          class="flex w-full items-start gap-3 border p-3 text-left hover:bg-muted/50 disabled:cursor-not-allowed disabled:opacity-60"
          :disabled="isIncompatible(stimulus)"
          @click="choose(stimulus.id)"
        >
          <div class="min-w-0 flex-1">
            <div class="mb-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span class="font-mono">#{{ stimulus.id }}</span>
              <span class="flex items-center gap-1"><Layers3 class="size-3.5" />{{ t('stimuli.questionCount', { count: stimulus.question_count }) }}</span>
              <Badge v-if="stimulus.visibility === 'private'" variant="outline" class="gap-1"><Lock class="size-3" />{{ t('materials.filters.private') }}</Badge>
              <span v-if="isIncompatible(stimulus)">{{ t('stimuli.targetPicker.incompatible') }}</span>
              <span v-if="stimulus.source" class="truncate">{{ stimulus.source }}</span>
            </div>
            <RichContent :content="stimulus.content" :empty-text="t('stimuli.emptyMaterial')" class="line-clamp-3 text-sm" />
          </div>
        </button>
        <p v-if="results.length === 0" class="py-16 text-center text-sm text-muted-foreground">{{ keyword.trim() ? t('stimuli.targetPicker.noMatch') : t('stimuli.targetPicker.empty') }}</p>
      </div>
      <div v-if="pages > 1" class="flex items-center justify-end gap-2 text-sm text-muted-foreground">
        <Button variant="outline" size="icon" :disabled="page <= 1" :title="t('common.prevPage')" :aria-label="t('common.prevPage')" @click="page--"><ChevronLeft class="size-4" /></Button>
        <span>{{ t('materials.pageInfo', { page, pages }) }}</span>
        <Button variant="outline" size="icon" :disabled="page >= pages" :title="t('common.nextPage')" :aria-label="t('common.nextPage')" @click="page++"><ChevronRight class="size-4" /></Button>
      </div>
    </DialogContent>
  </Dialog>
</template>
