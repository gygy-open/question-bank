<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type {
  Question,
  KnowledgePoint,
  ImportItem,
  Tag,
  TagCategory,
  Subject,
  QuestionType,
  OptionSpec,
} from '@/types'
import {
  Dialog,
  DialogScrollContent,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Plus, Trash2, Save, Loader2, Check, ChevronsUpDown, X } from '@lucide/vue'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { toast } from 'vue-sonner'
import KnowledgePointSelector from './KnowledgePointSelector.vue'
import MarkdownPreview from './MarkdownPreview.vue'
import TiptapEditor from './TiptapEditor.vue'
import AnswerEditor from './AnswerEditor.vue'
import AnswerDisplay from './AnswerDisplay.vue'
import RichEditor from './rich-editor/RichEditor.vue'
import RichContent from './rich-editor/RichContent.vue'
import {
  type QuestionDraft,
  buildQuestionPayload,
  createDefaultOptions,
  dbQuestionToDraft,
  generateOptionId,
  isChoiceType,
  nextOptionLabel,
  pruneAnswerOptionRef,
  validateQuestionDraft,
} from '@/lib/questionModel'

interface Props {
  open: boolean
  question?: ImportItem | Question | Partial<Question> | null
  knowledgePoints?: KnowledgePoint[]
  subjects?: Subject[]
  mode?: 'import' | 'create' | 'edit'
  autoFillSubjectId?: number | null
}

const props = withDefaults(defineProps<Props>(), {
  mode: 'create',
  autoFillSubjectId: null,
})

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
  (e: 'success', data: Question): void
  (e: 'save', question: ImportItem): void
}>()

const { $api } = useNuxtApp()

const isImportMode = computed(() => props.mode === 'import')

// 两套互斥的编辑态：import 走旧 Markdown 字符串 ImportItem；create/edit 走 v2 RichDoc 草稿。
const importItem = ref<ImportItem | null>(null)
const draft = ref<QuestionDraft | null>(null)

const isSubmitting = ref(false)
const openTagSelect = ref(false)

const activeSubjectId = computed<number | undefined>(
  () =>
    draft.value?.subject_id
    ?? importItem.value?.subject_id
    ?? props.autoFillSubjectId
    ?? undefined,
)

const { data: tags, refresh: refreshTags } = useAPI<Tag[]>('/tags', {
  query: computed(() => ({ subject_id: activeSubjectId.value || undefined })),
  immediate: false,
  watch: false,
})
const { data: tagCategories, refresh: refreshTagCategories } = useAPI<TagCategory[]>('/tag-categories', {
  query: computed(() => ({ subject_id: activeSubjectId.value || undefined })),
  immediate: false,
  watch: false,
})

watch(activeSubjectId, (newId) => {
  if (newId) {
    refreshTags()
    refreshTagCategories()
  }
}, { immediate: true })

const availableKnowledgePoints = computed(() => {
  if (!props.knowledgePoints) return []
  if (activeSubjectId.value) {
    return props.knowledgePoints.filter(kp => kp.subject_id == activeSubjectId.value)
  }
  return []
})

// --- shared field accessors (map to whichever edit state is active) ---
const qType = computed<QuestionType>({
  get: () => (isImportMode.value ? importItem.value?.q_type : draft.value?.q_type) ?? 'single_choice',
  set: (v) => {
    if (isImportMode.value) {
      if (importItem.value) importItem.value.q_type = v
    } else if (draft.value) {
      switchDraftType(draft.value, v)
    }
  },
})

const difficulty = computed<number>({
  get: () => (isImportMode.value ? importItem.value?.difficulty : draft.value?.difficulty) ?? 3,
  set: (v) => {
    if (isImportMode.value) { if (importItem.value) importItem.value.difficulty = v }
    else if (draft.value) draft.value.difficulty = v
  },
})

const knowledgePointIds = computed<number[]>({
  get: () =>
    (isImportMode.value ? importItem.value?.knowledge_point_ids : draft.value?.knowledge_point_ids) ?? [],
  set: (v) => {
    if (isImportMode.value) { if (importItem.value) importItem.value.knowledge_point_ids = v }
    else if (draft.value) draft.value.knowledge_point_ids = v
  },
})

// --- db draft type switching: reinit options + answer for the new variant ---
function switchDraftType(d: QuestionDraft, newType: QuestionType) {
  const oldType = d.q_type
  if (oldType === newType) return
  d.q_type = newType
  if (isChoiceType(newType) && d.options.length === 0) {
    d.options = createDefaultOptions()
  }
  d.answer = null
}

const initState = () => {
  openTagSelect.value = false
  if (isImportMode.value) {
    draft.value = null
    const src = props.question as ImportItem | null
    const item: ImportItem = src
      ? JSON.parse(JSON.stringify(src))
      : {
          id: 'temp-' + Date.now(),
          selected: true,
          content: '',
          q_type: 'single_choice',
          options: [
            { label: 'A', content: '' },
            { label: 'B', content: '' },
            { label: 'C', content: '' },
            { label: 'D', content: '' },
          ],
          answer: '',
          thinking: '',
          analysis: '',
          difficulty: 3,
          knowledge_point_ids: [],
          subject_id: props.autoFillSubjectId ?? undefined,
        }
    item.content = item.content || ''
    item.answer = typeof item.answer === 'string' ? item.answer : ''
    item.thinking = item.thinking || ''
    item.analysis = item.analysis || ''
    item.options = item.options || []
    item.knowledge_point_ids = item.knowledge_point_ids || []
    if (!item.subject_id && props.autoFillSubjectId) item.subject_id = props.autoFillSubjectId
    importItem.value = item
  } else {
    importItem.value = null
    const fallbackSubject =
      props.autoFillSubjectId
      ?? (props.subjects && props.subjects.length === 1 ? props.subjects[0].id : undefined)
      ?? undefined
    draft.value = dbQuestionToDraft(
      (props.question as Partial<Question>) ?? {},
      { subjectId: fallbackSubject },
    )
  }
}

watch(() => props.question, initState, { immediate: true })
watch(() => props.open, (isOpen) => { if (isOpen) initState() })
watch(() => props.mode, initState)

const title = computed(() => (props.mode === 'edit' ? '编辑题目' : '新增题目'))

// --- import option handlers (legacy string options) ---
const importAddOption = () => {
  if (!importItem.value) return
  importItem.value.options.push({ label: nextOptionLabel(importItem.value.options.length), content: '' })
}
const importRemoveOption = (index: number) => {
  importItem.value?.options.splice(index, 1)
}

// --- db draft option handlers (v2 OptionSpec with stable ids) ---
const draftAddOption = () => {
  if (!draft.value) return
  const opt: OptionSpec = {
    id: generateOptionId(),
    label: nextOptionLabel(draft.value.options.length),
    content: null,
  }
  draft.value.options.push(opt)
}
const draftRemoveOption = (index: number) => {
  if (!draft.value) return
  const [removed] = draft.value.options.splice(index, 1)
  // 重排 label（A/B/C…）并清理 answer 对被删选项的引用。
  draft.value.options.forEach((o, i) => { o.label = nextOptionLabel(i) })
  if (removed) draft.value.answer = pruneAnswerOptionRef(draft.value.answer, removed.id)
}

// --- save flows ---
const handleSaveImport = () => {
  if (!importItem.value) return
  emit('save', importItem.value)
  emit('update:open', false)
}

const handlePublish = async () => {
  if (!draft.value) return
  const error = validateQuestionDraft(draft.value)
  if (error) {
    toast.error(error)
    return
  }
  isSubmitting.value = true
  try {
    const payload = buildQuestionPayload(draft.value)
    let saved: Question
    if (props.mode === 'edit' && draft.value.id) {
      saved = await $api<Question>(`/questions/${draft.value.id}`, { method: 'PUT', body: payload })
    } else {
      saved = await $api<Question>('/questions', { method: 'POST', body: payload })
    }
    emit('success', saved)
    emit('update:open', false)
  } catch (err: unknown) {
    console.error(err)
    toast.error('保存失败', { description: err instanceof Error ? err.message : undefined })
  } finally {
    isSubmitting.value = false
  }
}

const handleClose = () => emit('update:open', false)

// MathLive 虚拟键盘渲染在弹窗之外，点击它会触发 Dialog 的“点击外部关闭”；目标在键盘内时阻止关闭。
const onInteractOutside = (event: Event) => {
  const detail = (event as CustomEvent).detail as { originalEvent?: Event } | undefined
  const target = (detail?.originalEvent?.target ?? event.target) as HTMLElement | null
  if (target?.closest?.('[class*="ML__keyboard"], [class*="MLK__"], [class*="ML__virtual-keyboard"]')) {
    event.preventDefault()
  }
}

// --- tags (db mode only) ---
const selectedTags = computed(() => {
  if (!tags.value || !draft.value) return []
  return tags.value.filter(t => draft.value!.tag_ids.includes(t.id))
})
const toggleTag = (tagId: number) => {
  if (!draft.value) return
  const idx = draft.value.tag_ids.indexOf(tagId)
  if (idx === -1) draft.value.tag_ids.push(tagId)
  else draft.value.tag_ids.splice(idx, 1)
}
</script>

<template>
  <Dialog :open="open" @update:open="handleClose">
    <DialogScrollContent
      :show-close-button="false"
      class="bg-background !my-0 !max-w-none !min-w-full !p-0 !rounded-none !border-none !shadow-none !min-h-screen lg:!h-screen lg:overflow-hidden"
      @interact-outside="onInteractOutside"
    >
      <div class="flex w-full flex-col bg-background min-h-screen lg:h-full">
        <!-- Header -->
        <div class="sticky top-0 z-50 flex items-center justify-between border-b border-border/50 px-6 py-4 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80 lg:static lg:bg-background">
          <DialogTitle class="text-lg">{{ isImportMode ? '编辑导入题目' : title }}</DialogTitle>
          <div class="flex items-center gap-2">
            <Button v-if="!isImportMode" size="sm" @click="handlePublish" :disabled="isSubmitting">
              <Loader2 v-if="isSubmitting" class="mr-2 h-4 w-4 animate-spin" />
              <Save v-else class="mr-2 h-4 w-4" />
              {{ mode === 'create' ? '保存' : '更新' }}
            </Button>
            <Button v-else size="sm" @click="handleSaveImport">
              <Save class="mr-2 h-4 w-4" />
              保存
            </Button>
            <Button variant="outline" size="sm" @click="handleClose">关闭</Button>
          </div>
        </div>

        <!-- Content -->
        <div class="flex-1 lg:min-h-0">
          <div class="grid gap-0 lg:grid-cols-[minmax(0,60%)_minmax(0,40%)] lg:h-full">
            <!-- Editor (Left) -->
            <section class="border-b border-border/50 bg-background px-6 py-6 lg:border-b-0 lg:border-r lg:h-full lg:overflow-y-auto">
              <div class="mx-auto max-w-3xl space-y-6">

                <!-- Type & Difficulty (+ db-only status/parent) -->
                <div class="grid grid-cols-2 gap-4">
                  <div class="space-y-2">
                    <Label>题目类型</Label>
                    <Select v-model="qType">
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="single_choice">单选题</SelectItem>
                        <SelectItem value="multiple_choice">多选题</SelectItem>
                        <SelectItem value="true_false">判断题</SelectItem>
                        <SelectItem value="fill_in_the_blank">填空题</SelectItem>
                        <SelectItem value="free_response">解答题</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div v-if="!isImportMode && draft" class="space-y-2">
                    <Label>状态</Label>
                    <Select v-model="draft.status">
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="draft">草稿</SelectItem>
                        <SelectItem value="pending">待审核</SelectItem>
                        <SelectItem value="published">已发布</SelectItem>
                        <SelectItem value="archived">已归档</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div class="space-y-2">
                    <Label>难度</Label>
                    <Select v-model.number="difficulty">
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem :value="1">难度 1</SelectItem>
                        <SelectItem :value="2">难度 2</SelectItem>
                        <SelectItem :value="3">难度 3</SelectItem>
                        <SelectItem :value="4">难度 4</SelectItem>
                        <SelectItem :value="5">难度 5</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div v-if="!isImportMode && draft" class="space-y-2">
                    <Label>父题目 ID (可选)</Label>
                    <Input v-model.number="draft.parent_id" type="number" placeholder="输入原题 ID" />
                  </div>
                </div>

                <!-- Source (db only) -->
                <div v-if="!isImportMode && draft" class="space-y-2">
                  <Label>来源</Label>
                  <Input v-model="draft.source" placeholder="输入题目来源" />
                </div>

                <!-- Knowledge Points -->
                <div class="space-y-2">
                  <Label>所属知识点</Label>
                  <div v-if="!activeSubjectId" class="text-xs text-muted-foreground mb-1">请先选择学科以加载知识点</div>
                  <KnowledgePointSelector
                    v-model="knowledgePointIds"
                    :knowledge-points="availableKnowledgePoints"
                    :disabled="!activeSubjectId"
                  />
                </div>

                <!-- Tags (db only) -->
                <div v-if="!isImportMode && draft" class="space-y-2">
                  <Label>标签</Label>
                  <div class="flex flex-wrap gap-2 mb-2" v-if="selectedTags.length > 0">
                    <Badge
                      v-for="tag in selectedTags"
                      :key="tag.id"
                      variant="secondary"
                      :style="{ backgroundColor: tag.color + '20', color: tag.color, borderColor: tag.color }"
                      class="border pl-2 pr-1 py-1 flex items-center gap-1"
                    >
                      {{ tag.name }}
                      <button class="hover:bg-background/50 rounded-full p-0.5 transition-colors" @click.stop="toggleTag(tag.id)">
                        <X class="h-3 w-3" />
                      </button>
                    </Badge>
                  </div>
                  <Popover v-model:open="openTagSelect">
                    <PopoverTrigger as-child>
                      <Button variant="outline" role="combobox" :aria-expanded="openTagSelect" class="w-full justify-between">
                        选择标签...
                        <ChevronsUpDown class="ml-2 h-4 w-4 shrink-0 opacity-50" />
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent class="w-[400px] p-0" align="start">
                      <Command>
                        <CommandInput placeholder="搜索标签..." />
                        <CommandEmpty>未找到标签</CommandEmpty>
                        <CommandList>
                          <CommandGroup v-for="cat in tagCategories" :key="cat.id" :heading="cat.name">
                            <CommandItem
                              v-for="tag in tags?.filter(t => t.category_id === cat.id)"
                              :key="tag.id"
                              :value="tag.name"
                              @select="toggleTag(tag.id)"
                            >
                              <Check :class="cn('mr-2 h-4 w-4', draft.tag_ids.includes(tag.id) ? 'opacity-100' : 'opacity-0')" />
                              <div class="flex items-center gap-2">
                                <div class="w-3 h-3 rounded-full" :style="{ backgroundColor: tag.color }"></div>
                                {{ tag.name }}
                              </div>
                            </CommandItem>
                          </CommandGroup>
                          <CommandGroup heading="其他">
                            <CommandItem
                              v-for="tag in tags?.filter(t => t.category_id == null || !tagCategories?.find(c => c.id === t.category_id))"
                              :key="tag.id"
                              :value="tag.name"
                              @select="toggleTag(tag.id)"
                            >
                              <Check :class="cn('mr-2 h-4 w-4', draft.tag_ids.includes(tag.id) ? 'opacity-100' : 'opacity-0')" />
                              <div class="flex items-center gap-2">
                                <div class="w-3 h-3 rounded-full" :style="{ backgroundColor: tag.color }"></div>
                                {{ tag.name }}
                              </div>
                            </CommandItem>
                          </CommandGroup>
                        </CommandList>
                      </Command>
                    </PopoverContent>
                  </Popover>
                </div>

                <!-- ================= IMPORT (legacy) editors ================= -->
                <template v-if="isImportMode && importItem">
                  <div class="space-y-2">
                    <Label>题干</Label>
                    <TiptapEditor v-model="importItem.content" />
                  </div>

                  <div v-if="qType === 'single_choice' || qType === 'multiple_choice'" class="space-y-2">
                    <Label>选项</Label>
                    <div class="grid grid-cols-1 gap-4">
                      <div v-for="(opt, optIndex) in importItem.options" :key="optIndex" class="flex gap-2 items-start">
                        <div class="w-8 h-9 flex items-center justify-center bg-muted rounded font-medium shrink-0 mt-0.5">{{ opt.label }}</div>
                        <div class="flex-1">
                          <TiptapEditor v-model="opt.content" min-height="min-h-[100px]" />
                        </div>
                        <Button variant="ghost" size="icon" class="h-8 w-8 mt-0.5" @click="importRemoveOption(optIndex)">
                          <Trash2 class="h-3 w-3" />
                        </Button>
                      </div>
                      <Button variant="outline" class="w-full border-dashed" @click="importAddOption">
                        <Plus class="h-4 w-4 mr-2" /> 添加选项
                      </Button>
                    </div>
                  </div>

                  <div class="space-y-2">
                    <Label>答案</Label>
                    <TiptapEditor v-model="importItem.answer" />
                  </div>

                  <div class="space-y-2">
                    <Label>分析</Label>
                    <TiptapEditor v-model="importItem.thinking" />
                  </div>
                  <div class="space-y-2">
                    <Label>解析</Label>
                    <TiptapEditor v-model="importItem.analysis" />
                  </div>
                </template>

                <!-- ================= CREATE/EDIT (v2) editors ================= -->
                <template v-else-if="draft">
                  <div class="space-y-2">
                    <Label>题干</Label>
                    <RichEditor v-model="draft.content" :allow-blank="qType === 'fill_in_the_blank'" />
                  </div>

                  <div v-if="qType === 'single_choice' || qType === 'multiple_choice'" class="space-y-2">
                    <Label>选项</Label>
                    <div class="grid grid-cols-1 gap-4">
                      <div v-for="(opt, optIndex) in draft.options" :key="opt.id" class="flex gap-2 items-start">
                        <div class="w-8 h-9 flex items-center justify-center bg-muted rounded font-medium shrink-0 mt-0.5">{{ opt.label }}</div>
                        <div class="flex-1">
                          <RichEditor v-model="opt.content" placeholder="输入选项内容…" />
                        </div>
                        <Button variant="ghost" size="icon" class="h-8 w-8 mt-0.5" @click="draftRemoveOption(optIndex)">
                          <Trash2 class="h-3 w-3" />
                        </Button>
                      </div>
                      <Button variant="outline" class="w-full border-dashed" @click="draftAddOption">
                        <Plus class="h-4 w-4 mr-2" /> 添加选项
                      </Button>
                    </div>
                  </div>

                  <AnswerEditor
                    v-model="draft.answer"
                    :q-type="draft.q_type"
                    :options="draft.options"
                    :stem="draft.content"
                  />

                  <div class="space-y-2">
                    <Label>分析</Label>
                    <RichEditor v-model="draft.thinking" />
                  </div>
                  <div class="space-y-2">
                    <Label>解析</Label>
                    <RichEditor v-model="draft.analysis" />
                  </div>
                  <div class="space-y-2">
                    <Label>总结</Label>
                    <RichEditor v-model="draft.summary" />
                  </div>
                </template>
              </div>
            </section>

            <!-- Preview (Right) -->
            <aside class="border-t border-border/50 bg-muted/20 px-6 py-6 lg:border-t-0 lg:border-l lg:h-full lg:overflow-y-auto">
              <div class="mx-auto max-w-3xl space-y-6">

                <!-- IMPORT preview: legacy Markdown -->
                <template v-if="isImportMode && importItem">
                  <div class="space-y-2">
                    <h3 class="font-semibold text-sm text-muted-foreground">题目预览</h3>
                    <div class="prose prose-sm max-w-none dark:prose-invert bg-background p-4 rounded border border-border">
                      <MarkdownPreview :content="importItem.content || '（空）'" />
                    </div>
                  </div>
                  <div v-if="(qType === 'single_choice' || qType === 'multiple_choice') && importItem.options.length > 0" class="space-y-2">
                    <h3 class="font-semibold text-sm text-muted-foreground">选项预览</h3>
                    <div class="space-y-2 bg-background p-4 rounded border border-border">
                      <div v-for="opt in importItem.options" :key="opt.label" class="flex gap-2">
                        <span class="font-bold text-muted-foreground shrink-0">{{ opt.label }}.</span>
                        <div class="flex-1 prose prose-sm [&_.prose]:my-0 [&_.prose>p]:my-0">
                          <MarkdownPreview :content="opt.content" />
                        </div>
                      </div>
                    </div>
                  </div>
                  <div class="space-y-2">
                    <h3 class="font-semibold text-sm text-muted-foreground">答案</h3>
                    <div class="prose prose-sm max-w-none dark:prose-invert bg-background p-4 rounded border border-border">
                      <MarkdownPreview :content="importItem.answer || '（未填写）'" />
                    </div>
                  </div>
                  <div v-if="importItem.thinking" class="space-y-2">
                    <h3 class="font-semibold text-sm text-muted-foreground">分析</h3>
                    <div class="prose prose-sm max-w-none dark:prose-invert bg-background p-4 rounded border border-border">
                      <MarkdownPreview :content="importItem.thinking" />
                    </div>
                  </div>
                  <div v-if="importItem.analysis" class="space-y-2">
                    <h3 class="font-semibold text-sm text-muted-foreground">解析</h3>
                    <div class="prose prose-sm max-w-none dark:prose-invert bg-background p-4 rounded border border-border">
                      <MarkdownPreview :content="importItem.analysis" />
                    </div>
                  </div>
                </template>

                <!-- CREATE/EDIT preview: v2 RichContent -->
                <template v-else-if="draft">
                  <div class="space-y-2">
                    <h3 class="font-semibold text-sm text-muted-foreground">题目预览</h3>
                    <div class="bg-background p-4 rounded border border-border">
                      <RichContent :content="draft.content" empty-text="（空）" />
                    </div>
                  </div>
                  <div v-if="(qType === 'single_choice' || qType === 'multiple_choice') && draft.options.length > 0" class="space-y-2">
                    <h3 class="font-semibold text-sm text-muted-foreground">选项预览</h3>
                    <div class="space-y-2 bg-background p-4 rounded border border-border">
                      <div v-for="opt in draft.options" :key="opt.id" class="flex gap-2">
                        <span class="font-bold text-muted-foreground shrink-0">{{ opt.label }}.</span>
                        <div class="flex-1 [&_.prose]:my-0 [&_.prose>p]:my-0">
                          <RichContent :content="opt.content" empty-text="（空选项）" />
                        </div>
                      </div>
                    </div>
                  </div>
                  <div class="space-y-2">
                    <h3 class="font-semibold text-sm text-muted-foreground">答案</h3>
                    <div class="bg-background p-4 rounded border border-border">
                      <AnswerDisplay :answer="draft.answer" :options="draft.options" empty-text="（未填写）" />
                    </div>
                  </div>
                  <div v-if="draft.thinking" class="space-y-2">
                    <h3 class="font-semibold text-sm text-muted-foreground">分析</h3>
                    <div class="bg-background p-4 rounded border border-border">
                      <RichContent :content="draft.thinking" />
                    </div>
                  </div>
                  <div v-if="draft.analysis" class="space-y-2">
                    <h3 class="font-semibold text-sm text-muted-foreground">解析</h3>
                    <div class="bg-background p-4 rounded border border-border">
                      <RichContent :content="draft.analysis" />
                    </div>
                  </div>
                  <div v-if="draft.summary" class="space-y-2">
                    <h3 class="font-semibold text-sm text-muted-foreground">总结</h3>
                    <div class="bg-background p-4 rounded border border-border">
                      <RichContent :content="draft.summary" />
                    </div>
                  </div>
                </template>
              </div>
            </aside>
          </div>
        </div>
      </div>
    </DialogScrollContent>
  </Dialog>
</template>
