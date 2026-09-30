<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type {
  Question,
  KnowledgePoint,
  TagCategory,
  TagPage,
  Subject,
  QuestionType,
} from '@/types'
import {
  Dialog,
  DialogScrollContent,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Save, Loader2, Check, ChevronsUpDown, X, Layers3 } from '@lucide/vue'
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
import QuestionDraftEditor from './QuestionDraftEditor.vue'
import StimulusTargetPickerDialog from './stimuli/StimulusTargetPickerDialog.vue'
import AnswerDisplay from './AnswerDisplay.vue'
import RichContent from './rich-editor/RichContent.vue'
import {
  type QuestionDraft,
  type ImportDraft,
  buildQuestionPayload,
  cloneImportDraft,
  createEmptyDraft,
  dbQuestionToDraft,
  hasOptionPool,
  validateQuestionDraft,
} from '@/lib/questionModel'

interface Props {
  open: boolean
  question?: ImportDraft | Question | Partial<Question> | null
  knowledgePoints?: KnowledgePoint[]
  subjects?: Subject[]
  mode?: 'import' | 'create' | 'edit'
  autoFillSubjectId?: number | null
  derivedFromQuestionId?: number | null
}

const props = withDefaults(defineProps<Props>(), {
  mode: 'create',
  autoFillSubjectId: null,
  derivedFromQuestionId: null,
})

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
  (e: 'success', data: Question): void
  (e: 'save', question: ImportDraft): void
}>()

const { $api } = useNuxtApp()

const isImportMode = computed(() => props.mode === 'import')

// 所有模式统一走 v2 RichDoc 草稿；import 模式只是不落库，保存时把草稿回抛给评审列表。
const draft = ref<QuestionDraft | null>(null)
// import 模式下随草稿一起回抛的列表态（列表 key / 选中 / 警告 / AI 建议标签）。
const importMeta = ref<Pick<ImportDraft, 'uid' | 'selected' | 'warnings' | 'ai_suggested_tags'> | null>(null)

const isSubmitting = ref(false)
const openTagSelect = ref(false)

const activeSubjectId = computed<number | undefined>(
  () =>
    draft.value?.subject_id
    ?? props.autoFillSubjectId
    ?? undefined,
)

const { data: tagsPage, refresh: refreshTags } = useAPI<TagPage>('/tags', {
  query: computed(() => ({ subject_id: activeSubjectId.value || undefined, size: -1 })), // 标签选择器需要全部标签，不分页
  immediate: false,
  watch: false,
})
const tags = computed(() => tagsPage.value?.items)
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

// --- shared field accessors (draft is the single edit state for all modes) ---
const qType = computed<QuestionType>(() => draft.value?.q_type ?? 'single_choice')

const knowledgePointIds = computed<number[]>({
  get: () => draft.value?.knowledge_point_ids ?? [],
  set: (v) => {
    if (draft.value) draft.value.knowledge_point_ids = v
  },
})

const initState = () => {
  openTagSelect.value = false
  if (isImportMode.value) {
    const fallbackSubject = props.autoFillSubjectId ?? undefined
    const src = props.question as ImportDraft | null
    const item = src ? cloneImportDraft(src) : { ...createEmptyDraft({ subjectId: fallbackSubject }), uid: 'temp-' + Date.now(), selected: true, warnings: [] } as ImportDraft
    if (!item.subject_id && fallbackSubject) item.subject_id = fallbackSubject
    importMeta.value = {
      uid: item.uid,
      selected: item.selected,
      warnings: item.warnings,
      ai_suggested_tags: item.ai_suggested_tags,
    }
    draft.value = item
  } else {
    importMeta.value = null
    const fallbackSubject =
      props.autoFillSubjectId
      ?? (props.subjects && props.subjects.length === 1 ? props.subjects[0]?.id : undefined)
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

const initialDraft = ref('')
watch(() => props.question, () => { initialDraft.value = JSON.stringify(draft.value) }, { immediate: true })
watch(() => props.open, (isOpen) => { if (isOpen) initialDraft.value = JSON.stringify(draft.value) })

const title = computed(() => (props.mode === 'edit' ? '编辑题目' : '新增题目'))

const canConvertToStimulus = computed(() => {
  const question = props.question as Partial<Question> | null | undefined
  return props.mode === 'edit' && typeof question?.id === 'number' && question.stimulus_id == null
})
const stimulusPickerOpen = ref(false)
const joinStimulus = async (stimulusId: number | null) => {
  if (draft.value && JSON.stringify(draft.value) !== initialDraft.value
    && !window.confirm('本题有未保存的修改，继续将丢弃这些修改。确定继续吗？')) return
  const questionId = String((props.question as Partial<Question>).id)
  emit('update:open', false)
  await navigateTo(stimulusId == null
    ? { path: '/materials/new', query: { from_question: questionId } }
    : { path: `/materials/${stimulusId}/edit`, query: { add_question: questionId } })
}

// --- save flows ---
// 导入评审保存不做硬校验：最终「确认导入」时再统一校验/降级，允许中途保存不完整草稿。
const handleSaveImport = () => {
  if (!draft.value || !importMeta.value) return
  emit('save', { ...(draft.value as ImportDraft), ...importMeta.value })
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
    } else if (props.derivedFromQuestionId) {
      saved = await $api<Question>(`/questions/${props.derivedFromQuestionId}/derived-questions`, { method: 'POST', body: payload })
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
            <Button
              v-if="canConvertToStimulus"
              variant="outline"
              size="sm"
              title="把本题加入已有材料题，或新建一道材料题"
              @click="stimulusPickerOpen = true"
            >
              <Layers3 class="mr-2 h-4 w-4" />
              加入材料题
            </Button>
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

                <QuestionDraftEditor v-if="draft" :model-value="draft">
                  <template v-if="!isImportMode" #meta>
                    <div class="space-y-2">
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
                  </template>
                  <template #fields>
                <!-- Source (db only) -->
                <div v-if="!isImportMode" class="space-y-2">
                  <Label>来源</Label>
                  <Input v-model="draft.source" placeholder="输入题目来源" />
                </div>

                <!-- Visibility (db only) -->
                <div v-if="!isImportMode" class="space-y-2">
                  <Label>可见性</Label>
                  <Select v-model="draft.visibility">
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="public">公开（学科内共享）</SelectItem>
                      <SelectItem value="private">私有（仅自己可见）</SelectItem>
                    </SelectContent>
                  </Select>
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
                <div v-if="!isImportMode" class="space-y-2">
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
                  </template>
                </QuestionDraftEditor>
              </div>
            </section>

            <!-- Preview (Right) -->
            <aside class="border-t border-border/50 bg-muted/20 px-6 py-6 lg:border-t-0 lg:border-l lg:h-full lg:overflow-y-auto">
              <div class="mx-auto max-w-3xl space-y-6">

                <!-- v2 preview: RichContent (all modes) -->
                <template v-if="draft">
                  <div class="space-y-2">
                    <h3 class="font-semibold text-sm text-muted-foreground">题目预览</h3>
                    <div class="bg-background p-4 rounded border border-border">
                      <RichContent :content="draft.content" empty-text="（空）" />
                    </div>
                  </div>
                  <div v-if="hasOptionPool(qType) && draft.options.length > 0" class="space-y-2">
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
  <StimulusTargetPickerDialog
    v-if="canConvertToStimulus"
    v-model:open="stimulusPickerOpen"
    :subject-id="(question as Partial<Question>).subject_id"
    :question-visibility="(question as Partial<Question>).visibility ?? 'public'"
    @select="joinStimulus"
  />
</template>
