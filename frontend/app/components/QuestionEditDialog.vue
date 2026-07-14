<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { Question, KnowledgePoint, ImportItem, Tag, TagCategory } from '@/types'
import {
  Dialog,
  DialogScrollContent,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Plus, Trash2, Save, FileText, Loader2, Check, ChevronsUpDown, X } from 'lucide-vue-next'
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
import KnowledgePointSelector from './KnowledgePointSelector.vue'
import MarkdownPreview from './MarkdownPreview.vue'
import TiptapEditor from './TiptapEditor.vue'
import AnswerEditor from './AnswerEditor.vue'

interface Props {
  open: boolean
  question?: ImportItem | Question | Partial<Question> | null
  knowledgePoints?: KnowledgePoint[]
  subjects?: any[]
  mode?: 'import' | 'create' | 'edit'
  autoFillSubjectId?: number | null
}

const props = withDefaults(defineProps<Props>(), {
  mode: 'create',
  autoFillSubjectId: null,
})

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
  (e: 'success', data: any): void
  (e: 'save', question: ImportItem): void
}>()

const { $api } = useNuxtApp()
const { data: tags } = useAPI<Tag[]>('/tags')
const { data: tagCategories } = useAPI<TagCategory[]>('/tag-categories')

const editingQuestion = ref<any>(null)
const isSubmitting = ref(false)
const openTagSelect = ref(false)

const availableKnowledgePoints = computed(() => {
  if (!props.knowledgePoints) return []
  if (editingQuestion.value?.subject_id) {
    // Use loose comparison or conversion to handle string/number mismatch
    return props.knowledgePoints.filter(kp => kp.subject_id == editingQuestion.value.subject_id)
  }
  // If no subject selected, return all knowledge points (or maybe empty? Let's return all for flexibility in import mode)
  // But usually we want to restrict. However, if the user hasn't picked a subject, showing nothing might be confusing.
  // Let's return empty to encourage subject selection, as KPs are subject-specific.
  return [] 
})

const initQuestion = () => {
  openTagSelect.value = false
  const newQuestion = props.question
  if (newQuestion) {
    editingQuestion.value = JSON.parse(JSON.stringify(newQuestion))

    // Ensure string fields are not null for TiptapEditor
    if (editingQuestion.value) {
      editingQuestion.value.content = editingQuestion.value.content || ''
      
      // Handle answer based on type
      if (editingQuestion.value.q_type === 'fill_in_the_blank') {
        try {
          if (typeof editingQuestion.value.answer === 'string') {
             editingQuestion.value.answer = JSON.parse(editingQuestion.value.answer)
          }
          if (!Array.isArray(editingQuestion.value.answer)) {
             editingQuestion.value.answer = [['']]
          }
        } catch (e) {
          editingQuestion.value.answer = [['']]
        }
      } else {
        editingQuestion.value.answer = editingQuestion.value.answer || ''
      }

      editingQuestion.value.thinking = editingQuestion.value.thinking || ''
      editingQuestion.value.analysis = editingQuestion.value.analysis || ''
      editingQuestion.value.summary = editingQuestion.value.summary || ''
      editingQuestion.value.source = editingQuestion.value.source || ''
      
      if (editingQuestion.value.options) {
        editingQuestion.value.options.forEach((opt: any) => {
          opt.content = opt.content || ''
        })
      }
    }

    // Ensure options exist
    if (editingQuestion.value && !editingQuestion.value.options) {
      editingQuestion.value.options = []
    }
    // Initialize knowledge_point_ids for database questions
    if (editingQuestion.value && (newQuestion as Question).knowledge_points && !editingQuestion.value.knowledge_point_ids) {
      editingQuestion.value.knowledge_point_ids = (newQuestion as Question).knowledge_points?.map(c => c.id) || []
    }
    // Initialize tag_ids for database questions
    if (editingQuestion.value && (newQuestion as Question).tags && !editingQuestion.value.tag_ids) {
      editingQuestion.value.tag_ids = (newQuestion as Question).tags?.map(t => t.id) || []
    }
    if (editingQuestion.value && !editingQuestion.value.status) {
      editingQuestion.value.status = 'draft'
    }
    
    // Handle partial initialization (e.g. for Decompose action)
    if (props.mode === 'create' && !editingQuestion.value.id) {
       // Fill in defaults if missing
       if (!editingQuestion.value.q_type) editingQuestion.value.q_type = 'single_choice'
       if (!editingQuestion.value.options) {
          editingQuestion.value.options = [
            { label: 'A', content: '' },
            { label: 'B', content: '' },
            { label: 'C', content: '' },
            { label: 'D', content: '' }
          ]
       }
       if (!editingQuestion.value.difficulty) editingQuestion.value.difficulty = 3
       if (!editingQuestion.value.knowledge_point_ids) editingQuestion.value.knowledge_point_ids = []
       if (!editingQuestion.value.tag_ids) editingQuestion.value.tag_ids = []
    }

    // Auto-fill subject_id if provided and missing
    if (editingQuestion.value && !editingQuestion.value.subject_id && props.autoFillSubjectId) {
      editingQuestion.value.subject_id = props.autoFillSubjectId
    }
    // If still no subject_id and subjects list is available and has only one item, auto-select it
    if (editingQuestion.value && !editingQuestion.value.subject_id && props.subjects && props.subjects.length === 1) {
      editingQuestion.value.subject_id = props.subjects[0].id
    }
  } else {
    // Initialize empty question - use a temporary object for creation
    editingQuestion.value = {
      id: 'temp-' + Date.now(),
      selected: false,
      content: '',
      q_type: 'single_choice',
      options: [
        { label: 'A', content: '' },
        { label: 'B', content: '' },
        { label: 'C', content: '' },
        { label: 'D', content: '' }
      ],
      answer: '',
      thinking: '',
      analysis: '',
      summary: '',
      source: '',
      difficulty: 3,
      status: 'draft',
      knowledge_point_ids: [],
      tag_ids: [],
      subject_id: props.autoFillSubjectId || undefined,
      parent_id: undefined
    }
  }
}

watch(() => props.question, initQuestion, { immediate: true })

watch(() => props.open, (isOpen) => {
  if (isOpen) {
    initQuestion()
  }
})

const title = computed(() => {
  return props.mode === 'edit' ? '编辑题目' : '新增题目'
})

const addOption = () => {
  if (!editingQuestion.value) return
  const labels = ['A', 'B', 'C', 'D', 'E', 'F', 'G']
  const nextLabel = labels[editingQuestion.value.options?.length || 0] || '?'
  if (!editingQuestion.value.options) {
    editingQuestion.value.options = []
  }
  editingQuestion.value.options.push({ label: nextLabel, content: '' })
}

const removeOption = (index: number) => {
  if (!editingQuestion.value?.options) return
  editingQuestion.value.options.splice(index, 1)
}

const handleSave = () => {
  if (!editingQuestion.value) return
  
  emit('save', editingQuestion.value)
  emit('update:open', false)
}

const handlePublish = async () => {
  if (!editingQuestion.value) return
  isSubmitting.value = true

  try {
    const payload = {
      content: editingQuestion.value.content,
      q_type: editingQuestion.value.q_type,
      options: (editingQuestion.value.q_type === 'single_choice' || editingQuestion.value.q_type === 'multiple_choice') ? editingQuestion.value.options : [],
      answer: editingQuestion.value.q_type === 'fill_in_the_blank' ? JSON.stringify(editingQuestion.value.answer) : editingQuestion.value.answer,
      thinking: editingQuestion.value.thinking,
      analysis: editingQuestion.value.analysis,
      summary: editingQuestion.value.summary,
      source: editingQuestion.value.source,
      difficulty: editingQuestion.value.difficulty,
      knowledge_point_ids: editingQuestion.value.knowledge_point_ids || [],
      tag_ids: editingQuestion.value.tag_ids || [],
      status: editingQuestion.value.status,
      subject_id: editingQuestion.value.subject_id,
      parent_id: editingQuestion.value.parent_id || null
    }

    if (props.mode === 'edit') {
      await $api(`/questions/${editingQuestion.value.id}`, {
        method: 'PUT',
        body: payload,
      })
    } else {
      await $api('/questions', {
        method: 'POST',
        body: payload,
      })
    }

    emit('success', editingQuestion.value)
    emit('update:open', false)
  } catch (error) {
    console.error(error)
  } finally {
    isSubmitting.value = false
  }
}

const handleClose = () => {
  emit('update:open', false)
}

const selectedTags = computed(() => {
  if (!tags.value || !editingQuestion.value?.tag_ids) return []
  return tags.value.filter(t => editingQuestion.value.tag_ids.includes(t.id))
})

const toggleTag = (tagId: number) => {
  if (!editingQuestion.value) return
  if (!editingQuestion.value.tag_ids) editingQuestion.value.tag_ids = []
  
  const index = editingQuestion.value.tag_ids.indexOf(tagId)
  if (index === -1) {
    editingQuestion.value.tag_ids.push(tagId)
  } else {
    editingQuestion.value.tag_ids.splice(index, 1)
  }
}

watch(() => editingQuestion.value?.q_type, (newType, oldType) => {
  if (!editingQuestion.value || !newType || !oldType || newType === oldType) return

  // Also handle options if switching to choice types
  if ((newType === 'single_choice' || newType === 'multiple_choice') && (!editingQuestion.value.options || editingQuestion.value.options.length === 0)) {
        editingQuestion.value.options = [
        { label: 'A', content: '' },
        { label: 'B', content: '' },
        { label: 'C', content: '' },
        { label: 'D', content: '' }
      ]
  }
})
</script>

<template>
  <Dialog :open="open" @update:open="handleClose">
    <DialogScrollContent
      :show-close-button="false"
      class="bg-background !my-0 !max-w-none !min-w-full !p-0 !rounded-none !border-none !shadow-none !min-h-screen lg:!h-screen lg:overflow-hidden"
    >
      <div class="flex w-full flex-col bg-background min-h-screen lg:h-full">
        <!-- Header -->
        <div class="sticky top-0 z-50 flex items-center justify-between border-b border-border/50 px-6 py-4 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80 lg:static lg:bg-background">
          <DialogTitle class="text-lg">{{ title }}</DialogTitle>
          <div class="flex items-center gap-2">
            <Button
              v-if="mode !== 'import'"
              size="sm"
              @click="handlePublish"
              :disabled="isSubmitting"
            >
              <Loader2 v-if="isSubmitting" class="mr-2 h-4 w-4 animate-spin" />
              <Save v-else class="mr-2 h-4 w-4" />
              {{ mode === 'create' ? '保存' : '更新' }}
            </Button>
            <Button
              v-if="mode === 'import'"
              size="sm"
              @click="handleSave"
              :disabled="isSubmitting"
            >
              <Save class="mr-2 h-4 w-4" />
              保存
            </Button>
            <Button variant="outline" size="sm" @click="handleClose">
              关闭
            </Button>
          </div>
        </div>

        <!-- Content -->
        <div class="flex-1 lg:min-h-0">
          <div class="grid gap-0 lg:grid-cols-[minmax(0,60%)_minmax(0,40%)] lg:h-full">
            <!-- Editor (Left) -->
            <section class="border-b border-border/50 bg-background px-6 py-6 lg:border-b-0 lg:border-r lg:h-full lg:overflow-y-auto">
              <div class="mx-auto max-w-3xl space-y-6">
              
              <!-- Subject Selection -->
              <div class="space-y-2" v-if="subjects && subjects.length > 0">
                <Label>所属学科</Label>
                <Select :model-value="editingQuestion?.subject_id?.toString()" @update:model-value="(v) => { if(editingQuestion) editingQuestion.subject_id = Number(v) }">
                  <SelectTrigger>
                    <SelectValue placeholder="选择学科" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem v-for="sub in subjects" :key="sub.id" :value="sub.id.toString()">
                      {{ sub.name }}
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <!-- Question Type & Difficulty -->
              <div class="grid grid-cols-2 gap-4">
                <div class="space-y-2">
                  <Label>题目类型</Label>
                  <Select v-model="editingQuestion!.q_type">
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="single_choice">单选题</SelectItem>
                      <SelectItem value="multiple_choice">多选题</SelectItem>
                      <SelectItem value="true_false">判断题</SelectItem>
                      <SelectItem value="fill_in_the_blank">填空题</SelectItem>
                      <SelectItem value="free_response">解答题</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div class="space-y-2">
                  <Label>状态</Label>
                  <Select v-model="editingQuestion!.status">
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
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
                  <Select v-model.number="editingQuestion!.difficulty">
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem :value="1">难度 1</SelectItem>
                      <SelectItem :value="2">难度 2</SelectItem>
                      <SelectItem :value="3">难度 3</SelectItem>
                      <SelectItem :value="4">难度 4</SelectItem>
                      <SelectItem :value="5">难度 5</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div class="space-y-2">
                  <Label>父题目 ID (可选)</Label>
                  <Input v-model.number="editingQuestion!.parent_id" type="number" placeholder="输入原题 ID" />
                </div>
              </div>

              <!-- Source -->
              <div class="space-y-2">
                <Label>来源</Label>
                <Input v-model="editingQuestion!.source" placeholder="输入题目来源" />
              </div>

              <!-- Knowledge Point Selection-->
              <div class="space-y-2">
                <Label>所属知识点</Label>
                <div v-if="!editingQuestion?.subject_id" class="text-xs text-muted-foreground mb-1">
                  请先选择学科以加载知识点
                </div>
                <KnowledgePointSelector
                  :model-value="(editingQuestion?.knowledge_point_ids || []) as number[]"
                  @update:model-value="(v) => {if(editingQuestion) editingQuestion.knowledge_point_ids = v}"
                  :knowledge-points="availableKnowledgePoints"
                  :disabled="!editingQuestion?.subject_id"
                />
              </div>

              <!-- Tag Selection -->
              <div class="space-y-2">
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
                    <Button
                      variant="outline"
                      role="combobox"
                      :aria-expanded="openTagSelect"
                      class="w-full justify-between"
                    >
                      选择标签...
                      <ChevronsUpDown class="ml-2 h-4 w-4 shrink-0 opacity-50" />
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent class="w-[400px] p-0" align="start">
                    <Command>
                      <CommandInput placeholder="搜索标签..." />
                      <CommandEmpty>未找到标签</CommandEmpty>
                      <CommandList>
                        <CommandGroup v-for="cat in tagCategories" :key="cat.slug" :heading="cat.name">
                          <CommandItem
                            v-for="tag in tags?.filter(t => t.category === cat.slug)"
                            :key="tag.id"
                            :value="tag.name"
                            @select="toggleTag(tag.id)"
                          >
                            <Check
                              :class="cn(
                                'mr-2 h-4 w-4',
                                editingQuestion?.tag_ids?.includes(tag.id) ? 'opacity-100' : 'opacity-0'
                              )"
                            />
                            <div class="flex items-center gap-2">
                                <div class="w-3 h-3 rounded-full" :style="{ backgroundColor: tag.color }"></div>
                                {{ tag.name }}
                            </div>
                          </CommandItem>
                        </CommandGroup>
                         <CommandGroup heading="其他">
                          <CommandItem
                            v-for="tag in tags?.filter(t => !t.category || !tagCategories?.find(c => c.slug === t.category))"
                            :key="tag.id"
                            :value="tag.name"
                            @select="toggleTag(tag.id)"
                          >
                            <Check
                              :class="cn(
                                'mr-2 h-4 w-4',
                                editingQuestion?.tag_ids?.includes(tag.id) ? 'opacity-100' : 'opacity-0'
                              )"
                            />
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

              <!-- Content -->
              <div class="space-y-2">
                <Label>题干</Label>
                <div>
                  <TiptapEditor v-model="editingQuestion!.content" />
                </div>
              </div>

              <!-- Options (for choice questions) -->
              <div v-if="editingQuestion!.q_type === 'single_choice' || editingQuestion!.q_type === 'multiple_choice'" class="space-y-2">
                <Label>选项</Label>
                <div class="grid grid-cols-1 gap-4">
                  <div v-for="(opt, optIndex) in editingQuestion!.options" :key="optIndex" class="flex gap-2 items-start">
                    <div class="w-8 h-9 flex items-center justify-center bg-muted rounded font-medium shrink-0 mt-0.5">
                      {{ opt.label }}
                    </div>
                    <div class="flex-1">
                      <TiptapEditor v-model="opt.content" min-height="min-h-[100px]" />
                    </div>
                    <Button variant="ghost" size="icon" class="h-8 w-8 mt-0.5" @click="removeOption(optIndex)">
                      <Trash2 class="h-3 w-3" />
                    </Button>
                  </div>
                  <Button variant="outline" class="w-full border-dashed" @click="addOption">
                    <Plus class="h-4 w-4 mr-2" /> 添加选项
                  </Button>
                </div>
              </div>

              <!-- Answer & Analysis -->
              <div class="space-y-2">
                <AnswerEditor 
                  v-model="editingQuestion!.answer" 
                  :q-type="editingQuestion!.q_type" 
                />
              </div>

              <div class="space-y-2">
                <Label>分析</Label>
                <div>
                  <TiptapEditor v-model="editingQuestion!.thinking" />
                </div>
              </div>

              <div class="space-y-2">
                <Label>解析</Label>
                <div>
                  <TiptapEditor v-model="editingQuestion!.analysis" />
                </div>
              </div>

              <div class="space-y-2">
                <Label>总结</Label>
                <div>
                  <TiptapEditor v-model="editingQuestion!.summary" />
                </div>
              </div>
            </div>
            </section>

            <!-- Preview (Right) -->
            <aside class="border-t border-border/50 bg-muted/20 px-6 py-6 lg:border-t-0 lg:border-l lg:h-full lg:overflow-y-auto">
              <div class="mx-auto max-w-3xl space-y-6">
              <div class="space-y-2">
                <h3 class="font-semibold text-sm text-gray-700">题目预览</h3>
                <div class="prose prose-sm max-w-none dark:prose-invert bg-background p-4 rounded border border-border">
                  <MarkdownPreview :content="editingQuestion!.content || '（空）'" />
                </div>
              </div>

              <!-- Preview Options -->
              <div v-if="(editingQuestion!.q_type === 'single_choice' || editingQuestion!.q_type === 'multiple_choice') && editingQuestion!.options && editingQuestion!.options.length > 0" class="space-y-2">
                <h3 class="font-semibold text-sm text-gray-700">选项预览</h3>
                <div class="space-y-2 bg-background p-4 rounded border border-border">
                  <div v-for="opt in editingQuestion!.options" :key="opt.label" class="flex gap-2">
                    <span class="font-bold text-gray-600 shrink-0">{{ opt.label }}.</span>
                    <div class="flex-1 prose prose-sm [&_.prose]:my-0 [&_.prose>p]:my-0">
                      <MarkdownPreview :content="opt.content" />
                    </div>
                  </div>
                </div>
              </div>

              <!-- Preview Answer -->
              <div class="space-y-2">
                <h3 class="font-semibold text-sm text-gray-700">答案</h3>
                <div class="prose prose-sm max-w-none dark:prose-invert bg-background p-4 rounded border border-border">
                  <div v-if="editingQuestion!.q_type === 'fill_in_the_blank' && Array.isArray(editingQuestion!.answer)" class="flex flex-col gap-2">
                    <div v-for="(blank, index) in editingQuestion!.answer" :key="index" class="flex items-start gap-2">
                      <span v-if="editingQuestion!.answer.length > 1" class="font-mono text-gray-500 shrink-0 mt-1.5">{{ Number(index) + 1 }}.</span>
                      <div class="flex flex-wrap gap-2 items-center">
                        <template v-if="Array.isArray(blank)">
                          <template v-for="(ans, ansIdx) in blank" :key="ansIdx">
                            <div class="text-xs bg-background px-2 py-1 rounded border font-medium [&_.prose]:my-0 [&_.prose>p]:my-0 [&_.prose]:text-xs">
                              <MarkdownPreview :content="ans" />
                            </div>
                            <span v-if="ansIdx < blank.length - 1" class="text-xs text-muted-foreground">或</span>
                          </template>
                        </template>
                        <div v-else class="text-xs bg-background px-2 py-1 rounded border font-medium [&_.prose]:my-0 [&_.prose>p]:my-0 [&_.prose]:text-xs">
                          <MarkdownPreview :content="blank" />
                        </div>
                      </div>
                    </div>
                  </div>
                  <MarkdownPreview v-else :content="editingQuestion!.answer || '（未填写）'" />
                </div>
              </div>

              <!-- Preview Thinking -->
              <div v-if="editingQuestion!.thinking" class="space-y-2">
                <h3 class="font-semibold text-sm text-gray-700">分析</h3>
                <div class="prose prose-sm max-w-none dark:prose-invert bg-background p-4 rounded border border-border">
                  <MarkdownPreview :content="editingQuestion!.thinking" />
                </div>
              </div>

              <!-- Preview Analysis -->
              <div v-if="editingQuestion!.analysis" class="space-y-2">
                <h3 class="font-semibold text-sm text-gray-700">解析</h3>
                <div class="prose prose-sm max-w-none dark:prose-invert bg-background p-4 rounded border border-border">
                  <MarkdownPreview :content="editingQuestion!.analysis" />
                </div>
              </div>

              <!-- Preview Summary -->
              <div v-if="editingQuestion!.summary" class="space-y-2">
                <h3 class="font-semibold text-sm text-gray-700">总结</h3>
                <div class="prose prose-sm max-w-none dark:prose-invert bg-background p-4 rounded border border-border">
                  <MarkdownPreview :content="editingQuestion!.summary" />
                </div>
              </div>
              </div>
            </aside>
          </div>
        </div>
      </div>
    </DialogScrollContent>
  </Dialog>
</template>
