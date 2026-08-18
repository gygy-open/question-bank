<script setup lang="ts">
import { ref, watch } from 'vue'
import { useDebounceFn } from '@vueuse/core'
import { Input } from '@/components/ui/input'
import { Loader2, FileQuestion } from '@lucide/vue'
import MarkdownPreview from '@/components/MarkdownPreview.vue'
import type { QuestionBrief } from '~/types'

interface QuestionPage {
  items: QuestionBrief[]
  total: number
}

const props = defineProps<{
  active: boolean
}>()

const emit = defineEmits<{
  pick: [question: QuestionBrief]
}>()

const { currentSubjectId } = useSubjectContext()
const { $api } = useNuxtApp()

const keyword = ref('')
const loading = ref(false)
const results = ref<QuestionBrief[]>([])

const search = useDebounceFn(async () => {
  loading.value = true
  try {
    const data = await $api<QuestionPage>('/questions', {
      query: { keyword: keyword.value || undefined, subject_id: currentSubjectId.value, page: 1, size: 8 },
    })
    results.value = data.items
  } catch {
    results.value = []
  } finally {
    loading.value = false
  }
}, 300)

watch(() => props.active, (v) => {
  if (v) {
    keyword.value = ''
    search()
  }
})
watch(keyword, search)
</script>

<template>
  <div>
    <Input v-model="keyword" placeholder="搜索题目内容..." class="h-8 text-sm mb-2" autofocus />
    <div v-if="loading" class="flex justify-center py-6">
      <Loader2 class="h-4 w-4 animate-spin text-muted-foreground" />
    </div>
    <div v-else-if="results.length === 0" class="py-6 text-center text-xs text-muted-foreground">
      没有找到匹配的题目
    </div>
    <div v-else class="max-h-72 overflow-y-auto space-y-1">
      <button
        v-for="q in results"
        :key="q.id"
        class="w-full flex items-start gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-muted transition-colors"
        @click="emit('pick', q)"
      >
        <FileQuestion class="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <div class="min-w-0 flex-1 line-clamp-2 [&_.prose]:my-0 [&_.prose>p]:my-0 text-xs">
          <MarkdownPreview :content="q.content" />
        </div>
      </button>
    </div>
  </div>
</template>
