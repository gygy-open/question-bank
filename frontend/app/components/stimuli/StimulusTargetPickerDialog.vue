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
        <DialogTitle>加入材料题</DialogTitle>
        <DialogDescription>选择本题要加入的材料题；本题会成为其中的一道小题，保存后生效。</DialogDescription>
      </DialogHeader>
      <button type="button" class="flex w-full items-center gap-3 border border-dashed p-3 text-left hover:bg-muted/50" @click="choose(null)">
        <Plus class="size-4 shrink-0 text-muted-foreground" />
        <div>
          <div class="text-sm font-medium">新建材料题</div>
          <div class="text-xs text-muted-foreground">补充一段材料，本题作为第 1 小题</div>
        </div>
      </button>
      <div class="relative">
        <Search class="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input v-model="keyword" class="pl-9" placeholder="搜索已有材料题的材料内容或来源" />
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
              <span class="flex items-center gap-1"><Layers3 class="size-3.5" />{{ stimulus.question_count }} 道小题</span>
              <Badge v-if="stimulus.visibility === 'private'" variant="outline" class="gap-1"><Lock class="size-3" />私有</Badge>
              <span v-if="isIncompatible(stimulus)">公开题不能加入私有材料题</span>
              <span v-if="stimulus.source" class="truncate">{{ stimulus.source }}</span>
            </div>
            <RichContent :content="stimulus.content" empty-text="（空材料）" class="line-clamp-3 text-sm" />
          </div>
        </button>
        <p v-if="results.length === 0" class="py-16 text-center text-sm text-muted-foreground">{{ keyword.trim() ? '没有匹配的材料题' : '还没有材料题' }}</p>
      </div>
      <div v-if="pages > 1" class="flex items-center justify-end gap-2 text-sm text-muted-foreground">
        <Button variant="outline" size="icon" :disabled="page <= 1" title="上一页" aria-label="上一页" @click="page--"><ChevronLeft class="size-4" /></Button>
        <span>第 {{ page }} / {{ pages }} 页</span>
        <Button variant="outline" size="icon" :disabled="page >= pages" title="下一页" aria-label="下一页" @click="page++"><ChevronRight class="size-4" /></Button>
      </div>
    </DialogContent>
  </Dialog>
</template>
