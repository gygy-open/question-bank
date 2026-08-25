<script setup lang="ts">
import { ref, watch } from 'vue'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Search, Loader2 } from '@lucide/vue'
import { richDocToPlainText } from '@/components/rich-editor/richDoc'
import { questionTypeLabel } from '@/lib/answerFormat'
import type { Question } from '@/types'

const props = defineProps<{
  open: boolean
  subjectId: number | null
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  select: [question: Question]
}>()

const { $api } = useNuxtApp()

const loading = ref(false)
const keyword = ref('')
const results = ref<Question[]>([])
let seq = 0

async function search() {
  if (!props.subjectId) {
    results.value = []
    return
  }
  const mine = ++seq
  loading.value = true
  try {
    const page = await $api<{ items: Question[] }>('/questions', {
      query: {
        subject_id: props.subjectId,
        keyword: keyword.value || undefined,
        size: 20,
        page: 1,
        root_only: true,
      },
    })
    if (mine === seq) results.value = page.items
  } catch {
    if (mine === seq) results.value = []
  } finally {
    if (mine === seq) loading.value = false
  }
}

let debounce: ReturnType<typeof setTimeout> | null = null
watch(keyword, () => {
  if (debounce) clearTimeout(debounce)
  debounce = setTimeout(search, 250)
})

watch(
  () => props.open,
  (v) => {
    if (v) {
      keyword.value = ''
      results.value = []
      search()
    }
  },
)

function pick(question: Question) {
  emit('select', question)
  emit('update:open', false)
}

function preview(q: Question): string {
  return richDocToPlainText(q.content) || '（无题干文本）'
}
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogContent class="max-w-2xl">
      <DialogHeader>
        <DialogTitle>插入题目</DialogTitle>
        <DialogDescription>从当前科目题库检索并选择一道题目插入画布。</DialogDescription>
      </DialogHeader>

      <div class="relative">
        <Search class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input v-model="keyword" placeholder="搜索题干关键字…" class="pl-9" />
      </div>

      <div v-if="loading" class="flex h-[360px] items-center justify-center">
        <Loader2 class="h-6 w-6 animate-spin text-muted-foreground" />
      </div>

      <div
        v-else-if="results.length === 0"
        class="flex h-[360px] items-center justify-center text-sm text-muted-foreground"
      >
        没有匹配的题目
      </div>

      <ScrollArea v-else class="h-[360px] pr-3">
        <div class="space-y-2">
          <button
            v-for="q in results"
            :key="q.id"
            class="w-full rounded-lg border p-3 text-left transition-colors hover:border-primary hover:bg-muted/50"
            @click="pick(q)"
          >
            <div class="mb-1 flex items-center gap-2">
              <Badge variant="secondary" class="text-xs">{{ questionTypeLabel(q.q_type) }}</Badge>
              <span class="text-xs text-muted-foreground">#{{ q.id }}</span>
            </div>
            <p class="line-clamp-2 text-sm">{{ preview(q) }}</p>
          </button>
        </div>
      </ScrollArea>
    </DialogContent>
  </Dialog>
</template>
