<script setup lang="ts">
import { ref, watch } from 'vue'
import { ChevronLeft, ChevronRight, Loader2, Search } from '@lucide/vue'
import RichContent from '@/components/rich-editor/RichContent.vue'
import ClearableSelect from '@/components/ClearableSelect.vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { questionTypeLabel } from '@/lib/answerFormat'
import type { Question, QuestionPage } from '@/types'

const props = defineProps<{
  open: boolean
  subjectId: number | null
  selectedIds: number[]
  groupVisibility?: 'public' | 'private'
}>()
const emit = defineEmits<{ 'update:open': [value: boolean], select: [questions: Question[]] }>()
const { $api } = useNuxtApp()
const keyword = ref('')
const qType = ref('0')
const status = ref('0')
const page = ref(1)
const pages = ref(0)
const results = ref<Question[]>([])
const picked = ref<Map<number, Question>>(new Map())
const loading = ref(false)
let debounce: ReturnType<typeof setTimeout> | undefined
const typeOptions = [{ label: '全部题型', value: '0' }, { label: '单选题', value: 'single_choice' }, { label: '多选题', value: 'multiple_choice' }, { label: '判断题', value: 'true_false' }, { label: '填空题', value: 'fill_in_the_blank' }, { label: '解答题', value: 'free_response' }]
const statusOptions = [{ label: '全部状态', value: '0' }, { label: '草稿', value: 'draft' }, { label: '待审核', value: 'pending' }, { label: '已发布', value: 'published' }, { label: '已归档', value: 'archived' }]

const load = async () => {
  if (!props.subjectId) return
  loading.value = true
  try {
    const response = await $api<QuestionPage>('/questions', { query: { subject_id: props.subjectId, page: page.value, size: 10, keyword: keyword.value.trim() || undefined, q_type: qType.value === '0' ? undefined : qType.value, status: status.value === '0' ? undefined : status.value, root_only: true } })
    results.value = response.items
    pages.value = response.pages
  } finally { loading.value = false }
}
watch(() => props.open, open => { if (open) { page.value = 1; picked.value = new Map(); load() } })
watch(keyword, () => { clearTimeout(debounce); debounce = setTimeout(() => { page.value = 1; load() }, 250) })
watch([qType, status], () => { page.value = 1; load() })
watch(page, load)
watch(() => props.groupVisibility, (visibility) => {
  if (visibility === 'public') {
    picked.value = new Map([...picked.value].filter(([, question]) => question.visibility !== 'private'))
  }
})
const isIncompatible = (question: Question) => props.groupVisibility === 'public' && question.visibility === 'private'
const toggle = (question: Question) => {
  if (props.selectedIds.includes(question.id) || isIncompatible(question)) return
  const next = new Map(picked.value)
  if (next.has(question.id)) next.delete(question.id); else next.set(question.id, question)
  picked.value = next
}
const confirm = () => { emit('select', [...picked.value.values()]); emit('update:open', false) }
</script>

<template><Dialog :open="open" @update:open="emit('update:open', $event)"><DialogContent class="max-w-3xl"><DialogHeader><DialogTitle>选择题目</DialogTitle><DialogDescription>已在题组中的题目不可重复添加，公开题组不能选择私有题目。</DialogDescription></DialogHeader>
  <div class="grid gap-2 sm:grid-cols-[1fr_150px_150px]"><div class="relative"><Search class="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" /><Input v-model="keyword" class="pl-9" placeholder="搜索题干" /></div><ClearableSelect v-model="qType" :options="typeOptions" /><ClearableSelect v-model="status" :options="statusOptions" /></div>
  <div v-if="loading" class="flex h-80 items-center justify-center"><Loader2 class="size-6 animate-spin" /></div><div v-else class="h-80 space-y-2 overflow-y-auto"><button v-for="question in results" :key="question.id" type="button" class="flex w-full items-start gap-3 border p-3 text-left hover:bg-muted/50 disabled:cursor-not-allowed disabled:opacity-60" :disabled="selectedIds.includes(question.id) || isIncompatible(question)" @click="toggle(question)"><Checkbox :checked="selectedIds.includes(question.id) || picked.has(question.id)" class="mt-1" /><div class="min-w-0 flex-1"><div class="mb-1 flex flex-wrap gap-2"><Badge variant="outline">#{{ question.id }}</Badge><Badge variant="secondary">{{ questionTypeLabel(question.q_type) }}</Badge><Badge variant="outline">{{ question.status }}</Badge><Badge v-if="question.visibility === 'private'" variant="outline">私有</Badge><Badge v-if="selectedIds.includes(question.id)" variant="outline">已在题组</Badge></div><RichContent :content="question.content" class="line-clamp-3 text-sm" /></div></button><p v-if="results.length === 0" class="py-16 text-center text-sm text-muted-foreground">没有匹配题目</p></div>
  <DialogFooter class="items-center sm:justify-between"><div class="flex items-center gap-2"><Button variant="outline" size="icon" :disabled="page <= 1" aria-label="上一页" @click="page--"><ChevronLeft class="size-4" /></Button><span class="text-sm">{{ page }} / {{ Math.max(pages, 1) }}</span><Button variant="outline" size="icon" :disabled="page >= pages" aria-label="下一页" @click="page++"><ChevronRight class="size-4" /></Button></div><Button :disabled="picked.size === 0" @click="confirm">添加 {{ picked.size }} 道题</Button></DialogFooter>
</DialogContent></Dialog></template>