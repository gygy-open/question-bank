<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Search, Loader2, SlidersHorizontal, ListTree, ChevronsUpDown, ExternalLink, X } from '@lucide/vue'
import RichContent from '@/components/rich-editor/RichContent.vue'
import KnowledgePointTreeSelector from '@/components/KnowledgePointTreeSelector.vue'
import TagFilter from '@/components/TagFilter.vue'
import ClearableSelect from '@/components/ClearableSelect.vue'
import { questionTypeLabel } from '@/lib/answerFormat'
import type { Question, KnowledgePoint, Tag, TagCategory } from '@/types'

const props = defineProps<{
  open: boolean
  subjectId: number | null
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  select: [questions: Question[]]
}>()

const { $api } = useNuxtApp()

const loading = ref(false)
const keyword = ref('')
const results = ref<Question[]>([])
const selected = ref<Map<number, Question>>(new Map())
let seq = 0

// --- Filters (knowledge point / tag / type / difficulty; kept lean vs. /questions) ---
const filtersExpanded = ref(false)
const kpPopoverOpen = ref(false)
const qType = ref<string | undefined>(undefined)
const difficulty = ref<string | undefined>(undefined)
const knowledgePointIds = ref<string[]>([])
const tagIds = ref<string[]>([])

const qTypeOptions = [
  { label: '全部题型', value: '0' },
  { label: '单选题', value: 'single_choice' },
  { label: '多选题', value: 'multiple_choice' },
  { label: '判断题', value: 'true_false' },
  { label: '填空题', value: 'fill_in_the_blank' },
  { label: '解答题', value: 'free_response' },
]
const difficultyOptions = [
  { label: '全部难度', value: '0' },
  { label: '1', value: '1' },
  { label: '2', value: '2' },
  { label: '3', value: '3' },
  { label: '4', value: '4' },
  { label: '5', value: '5' },
]

const activeFilterCount = computed(() => {
  let count = 0
  if (qType.value && qType.value !== '0') count++
  if (difficulty.value && difficulty.value !== '0') count++
  if (knowledgePointIds.value.length > 0) count++
  if (tagIds.value.length > 0) count++
  return count
})

function resetFilters() {
  qType.value = undefined
  difficulty.value = undefined
  knowledgePointIds.value = []
  tagIds.value = []
}

function toggleKnowledgePoint(id: string) {
  const idx = knowledgePointIds.value.indexOf(id)
  if (idx >= 0) knowledgePointIds.value.splice(idx, 1)
  else knowledgePointIds.value.push(id)
}
function clearKnowledgePoints() {
  knowledgePointIds.value = []
}

// --- Filter option data, lazily fetched per subject on first open ---
const knowledgePoints = ref<KnowledgePoint[]>([])
const tags = ref<Tag[]>([])
const tagCategories = ref<TagCategory[]>([])
let loadedForSubjectId: number | null = null

const filteredKnowledgePoints = computed(() =>
  knowledgePoints.value.filter((kp) => kp.subject_id === props.subjectId),
)
const knowledgePointFilterLabel = computed(() => {
  const names = knowledgePointIds.value
    .map((id) => knowledgePoints.value.find((kp) => String(kp.id) === id)?.name)
    .filter((name): name is string => Boolean(name))
  if (names.length === 0) return '全部知识点'
  if (names.length === 1) return names[0]
  return `已选 ${names.length} 个`
})

async function loadFilterOptions() {
  if (!props.subjectId || loadedForSubjectId === props.subjectId) return
  loadedForSubjectId = props.subjectId
  try {
    const [kpRes, tagRes, catRes] = await Promise.all([
      $api<KnowledgePoint[]>('/knowledge-points', { query: { limit: -1 } }),
      $api<Tag[]>('/tags', { query: { subject_id: props.subjectId } }),
      $api<TagCategory[]>('/tag-categories', { query: { subject_id: props.subjectId } }),
    ])
    knowledgePoints.value = kpRes
    tags.value = tagRes
    tagCategories.value = catRes
  } catch {
    // 筛选选项加载失败不影响基础检索，静默忽略
  }
}

async function search() {
  if (!props.subjectId) {
    results.value = []
    return
  }
  const mine = ++seq
  loading.value = true
  try {
    const query: Record<string, unknown> = {
      subject_id: props.subjectId,
      keyword: keyword.value || undefined,
      size: 20,
      page: 1,
      root_only: true,
    }
    if (qType.value && qType.value !== '0') query.q_type = qType.value
    if (difficulty.value && difficulty.value !== '0') query.difficulty = difficulty.value
    if (knowledgePointIds.value.length > 0) query.knowledge_point_ids = knowledgePointIds.value
    if (tagIds.value.length > 0) query.tag_ids = tagIds.value
    const page = await $api<{ items: Question[] }>('/questions', { query })
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
watch([qType, difficulty, knowledgePointIds, tagIds], () => search(), { deep: true })

watch(
  () => props.open,
  (v) => {
    if (v) {
      keyword.value = ''
      results.value = []
      selected.value = new Map()
      resetFilters()
      filtersExpanded.value = false
      loadFilterOptions()
      search()
    }
  },
)

function toggleSelect(q: Question) {
  if (selected.value.has(q.id)) selected.value.delete(q.id)
  else selected.value.set(q.id, q)
}

function confirmInsert() {
  emit('select', Array.from(selected.value.values()))
  emit('update:open', false)
}
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogContent class="max-w-3xl">
      <DialogHeader>
        <DialogTitle class="flex items-center justify-between gap-2 pr-6">
          <span>插入题目</span>
          <NuxtLink
            to="/questions"
            target="_blank"
            class="inline-flex items-center gap-1 text-xs font-normal text-muted-foreground hover:text-primary"
          >
            在题库中打开
            <ExternalLink class="h-3 w-3" />
          </NuxtLink>
        </DialogTitle>
        <DialogDescription>从当前科目题库检索并选择题目插入画布，支持多选。</DialogDescription>
      </DialogHeader>

      <div class="flex items-center gap-2">
        <div class="relative flex-1">
          <Search class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input v-model="keyword" placeholder="搜索题干关键字…" class="pl-9" />
        </div>
        <Button variant="outline" size="sm" @click="filtersExpanded = !filtersExpanded">
          <SlidersHorizontal class="mr-2 h-4 w-4" />
          筛选
          <Badge v-if="activeFilterCount > 0" variant="secondary" class="ml-1.5 px-1.5">
            {{ activeFilterCount }}
          </Badge>
        </Button>
      </div>

      <div v-if="filtersExpanded" class="flex flex-wrap items-end gap-3 rounded-lg border bg-muted/30 p-3">
        <div class="w-32 space-y-1">
          <span class="text-xs font-medium text-muted-foreground">题型</span>
          <ClearableSelect v-model="qType" :options="qTypeOptions" placeholder="全部题型" />
        </div>
        <div class="w-28 space-y-1">
          <span class="text-xs font-medium text-muted-foreground">难度</span>
          <ClearableSelect v-model="difficulty" :options="difficultyOptions" placeholder="全部难度" />
        </div>
        <div class="min-w-[180px] flex-1 space-y-1">
          <span class="text-xs font-medium text-muted-foreground">知识点</span>
          <Popover v-model:open="kpPopoverOpen">
            <PopoverTrigger as-child>
              <Button variant="outline" role="combobox" class="h-9 w-full justify-between font-normal">
                <span class="flex items-center truncate">
                  <ListTree class="mr-2 h-4 w-4 shrink-0 opacity-50" />
                  <span class="truncate">{{ knowledgePointFilterLabel }}</span>
                </span>
                <ChevronsUpDown class="h-4 w-4 shrink-0 opacity-50" />
              </Button>
            </PopoverTrigger>
            <PopoverContent class="w-80 p-2" align="start">
              <div class="max-h-72 overflow-y-auto">
                <KnowledgePointTreeSelector
                  :knowledge-points="filteredKnowledgePoints"
                  :selected-ids="knowledgePointIds"
                  @toggle="toggleKnowledgePoint"
                  @clear="clearKnowledgePoints"
                />
              </div>
            </PopoverContent>
          </Popover>
        </div>
        <div class="min-w-[200px] flex-1 space-y-1">
          <span class="text-xs font-medium text-muted-foreground">标签</span>
          <TagFilter v-model="tagIds" :tags="tags" :categories="tagCategories" />
        </div>
        <Button v-if="activeFilterCount > 0" variant="ghost" size="sm" @click="resetFilters">
          <X class="mr-1 h-3.5 w-3.5" />
          重置
        </Button>
      </div>

      <div v-if="loading" class="flex h-[420px] items-center justify-center">
        <Loader2 class="h-6 w-6 animate-spin text-muted-foreground" />
      </div>

      <div
        v-else-if="results.length === 0"
        class="flex h-[420px] items-center justify-center text-sm text-muted-foreground"
      >
        没有匹配的题目
      </div>

      <ScrollArea v-else class="h-[420px] pr-3">
        <div class="space-y-2">
          <button
            v-for="q in results"
            :key="q.id"
            type="button"
            class="flex w-full items-start gap-3 rounded-lg border p-3 text-left transition-colors hover:border-primary hover:bg-muted/50"
            :class="selected.has(q.id) ? 'border-primary bg-primary/5' : ''"
            @click="toggleSelect(q)"
          >
            <Checkbox :checked="selected.has(q.id)" class="mt-1 shrink-0" @click.stop="toggleSelect(q)" />
            <div class="min-w-0 flex-1">
              <div class="mb-1 flex flex-wrap items-center gap-1.5">
                <Badge variant="secondary" class="text-xs">{{ questionTypeLabel(q.q_type) }}</Badge>
                <Badge variant="outline" class="text-xs">难度 {{ q.difficulty }}</Badge>
                <span class="text-xs text-muted-foreground">#{{ q.id }}</span>
                <Badge v-for="kp in q.knowledge_points" :key="`kp-${kp.id}`" variant="outline" class="text-xs">
                  {{ kp.name }}
                </Badge>
                <Badge v-for="tag in q.tags" :key="`tag-${tag.id}`" variant="outline" class="text-xs">
                  {{ tag.name }}
                </Badge>
              </div>
              <RichContent
                :content="q.content"
                empty-text="（无题干文本）"
                class="line-clamp-2 text-sm [&_.prose]:my-0"
              />
            </div>
          </button>
        </div>
      </ScrollArea>

      <div class="flex items-center justify-between border-t pt-3">
        <span class="text-sm text-muted-foreground">已选 {{ selected.size }} 题</span>
        <div class="flex gap-2">
          <Button v-if="selected.size > 0" variant="ghost" size="sm" @click="selected.clear()">清空</Button>
          <Button size="sm" :disabled="selected.size === 0" @click="confirmInsert">插入</Button>
        </div>
      </div>
    </DialogContent>
  </Dialog>
</template>
