<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import type { Question, KnowledgePoint, Tag, TagCategory, Subject, QuestionPage, User } from '~/types'
import { useAPI } from '~/composables/useAPI'
import KnowledgePointTreeSelector from '~/components/KnowledgePointTreeSelector.vue'
import QuestionListItem from '~/components/QuestionListItem.vue'
import QuestionEditDialog from '~/components/QuestionEditDialog.vue'
import QuestionStructureSheet from '~/components/QuestionStructureSheet.vue'
import PageHeader from '~/components/PageHeader.vue'
import PaperBasket from '~/components/PaperBasket.vue'
import TagFilter from '~/components/TagFilter.vue'
import { Loader2, Plus, X, Trash2, ShoppingBasket, ListTree, Edit } from 'lucide-vue-next'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet'
import {
  Pagination,
  PaginationEllipsis,
  PaginationFirst,
  PaginationLast,
  PaginationContent,
  PaginationItem,
  PaginationNext,
  PaginationPrevious,
} from '@/components/ui/pagination'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import ClearableInput from '@/components/ClearableInput.vue'
import ClearableSelect from '@/components/ClearableSelect.vue'
import { usePaperBasket } from '~/composables/usePaperBasket'
import { toast } from 'vue-sonner'


const { $api } = useNuxtApp()
const route = useRoute()
const router = useRouter()

// --- State ---
const page = ref(1)
const pageSize = ref(10)
const editingQuestion = ref<Question | null>(null)
const isDialogOpen = ref(false)
const dialogMode = ref<'create' | 'edit'>('create')

// --- Selection & Batch Actions ---
const selectedIds = ref<Set<number>>(new Set())
const { add: addToBasket, remove: removeFromBasket } = usePaperBasket()

// --- Filters ---
const filters = reactive({
  subject_id: undefined as string | undefined,
  knowledge_point_id: undefined as string | undefined,
  tag_ids: [] as string[],
  q_type: undefined as string | undefined,
  difficulty: undefined as string | undefined,
  status: undefined as string | undefined,
  import_task_id: undefined as string | undefined,
  import_task_name: undefined as string | undefined,
  review_count: undefined as string | undefined,
  creator_id: undefined as string | undefined,
  reviewer_id: undefined as string | undefined,
  keyword: undefined as string | undefined,
  id: undefined as string | undefined,
  source: undefined as string | undefined,
  root_only: false,
})

// Initialize filters from route query
if (route.query.import_task_id) {
    filters.import_task_id = route.query.import_task_id as string
}
if (route.query.id) {
    filters.id = route.query.id as string
}

// --- Data Fetching ---
const { data: subjects, refresh: refreshSubjects } = await useAPI<Subject[]>('/subjects')

const selectedSubjectId = ref<string>('0')
if (subjects.value?.[0]) {
  selectedSubjectId.value = String(subjects.value[0].id)
  filters.subject_id = selectedSubjectId.value
}

watch(selectedSubjectId, (newVal) => {
  filters.subject_id = newVal
  page.value = 1 // Reset page on subject change
})

const queryParams = computed(() => {
  const params: Record<string, any> = {
    page: page.value,
    size: pageSize.value
  }
  if (filters.id) {
    params.id = filters.id
  } else {
    if (filters.subject_id && filters.subject_id !== '0') params.subject_id = filters.subject_id
  }
  
  if (filters.knowledge_point_id && filters.knowledge_point_id !== '0') params.knowledge_point_id = filters.knowledge_point_id
  if (filters.tag_ids && filters.tag_ids.length > 0) params.tag_ids = filters.tag_ids
  if (filters.q_type && filters.q_type !== '0') params.q_type = filters.q_type
  if (filters.difficulty && filters.difficulty !== '0') params.difficulty = filters.difficulty
  if (filters.status && filters.status !== '0') params.status = filters.status
  if (filters.import_task_id) params.import_task_id = filters.import_task_id
  if (filters.import_task_name) params.import_task_name = filters.import_task_name
  if (filters.review_count) params.review_count = filters.review_count
  if (filters.creator_id && filters.creator_id !== '0') params.creator_id = filters.creator_id
  if (filters.reviewer_id && filters.reviewer_id !== '0') params.reviewer_id = filters.reviewer_id
  if (filters.keyword) params.keyword = filters.keyword
  if (filters.source) params.source = filters.source
  if (filters.root_only) params.root_only = true
  
  return params
})

const { data: questionPage, refresh: refreshQuestions, status: questionsStatus } = await useAPI<QuestionPage>('/questions', {
  query: queryParams
})

const questions = computed(() => questionPage.value?.items || [])
const total = computed(() => questionPage.value?.total || 0)

// --- Selection Logic ---
const isAllPageSelected = computed(() => {
  if (questions.value.length === 0) return false
  return questions.value.every(q => selectedIds.value.has(q.id))
})

const toggleAllPage = (checked: boolean) => {
  if (checked) {
    questions.value.forEach(q => selectedIds.value.add(q.id))
  } else {
    questions.value.forEach(q => selectedIds.value.delete(q.id))
  }
}

const invertSelection = () => {
  questions.value.forEach(q => {
    if (selectedIds.value.has(q.id)) {
      selectedIds.value.delete(q.id)
    } else {
      selectedIds.value.add(q.id)
    }
  })
}

const handleSelect = (id: number, selected: boolean) => {
  if (selected) {
    selectedIds.value.add(id)
  } else {
    selectedIds.value.delete(id)
  }
}

const batchAddToBasket = () => {
  let count = 0
  questions.value.forEach(q => {
    if (selectedIds.value.has(q.id)) {
      addToBasket({
        id: q.id,
        content: q.content,
        q_type: q.q_type
      })
      count++
    }
  })
  toast.success(`已将 ${count} 道题目加入试题栏`)
  selectedIds.value.clear()
}

const batchDelete = async () => {
  const ids = Array.from(selectedIds.value)
  if (ids.length === 0) return
  
  if (!confirm(`确定要删除选中的 ${ids.length} 道题目吗？此操作不可恢复。`)) return
  
  try {
    const res = await $api<{ deleted_count: number }>('/questions/batch-delete', {
      method: 'POST',
      body: { ids }
    })
    
    // Remove from basket if present
    ids.forEach(id => removeFromBasket(id))
    
    toast.success(`已删除 ${res.deleted_count} 道题目`)
    selectedIds.value.clear()
    refreshQuestions()
  } catch (error) {
    console.error(error)
    toast.error('批量删除失败')
  }
}

// --- Batch Update Source ---
const isSourceDialogOpen = ref(false)
const newSourceValue = ref('')

const openBatchUpdateSourceDialog = () => {
  if (selectedIds.value.size === 0) return
  newSourceValue.value = ''
  isSourceDialogOpen.value = true
}

const batchUpdateSource = async () => {
  const ids = Array.from(selectedIds.value)
  if (ids.length === 0) return
  
  try {
    const res = await $api<{ updated_count: number }>('/questions/batch-update', {
      method: 'POST',
      body: { 
        ids,
        source: newSourceValue.value
      }
    })
    
    toast.success(`已更新 ${res.updated_count} 道题目的来源`)
    isSourceDialogOpen.value = false
    selectedIds.value.clear()
    refreshQuestions()
  } catch (error) {
    console.error(error)
    toast.error('批量更新来源失败')
  }
}

// Clear selection when page changes
watch([page, pageSize], () => {
  selectedIds.value.clear()
})

// Auto-select subject tab if viewing a task and no subject selected
watch(questions, (newQuestions) => {
  if ((filters.import_task_id || filters.import_task_name) && newQuestions.length > 0 && !selectedSubjectId.value) {
    const firstQ = newQuestions[0]
    if (firstQ.subject_id) {
      selectedSubjectId.value = String(firstQ.subject_id)
    }
  }
}, { immediate: true })

const { data: knowledgePoints, refresh: refreshKnowledgePoints } = await useAPI<KnowledgePoint[]>('/knowledge-points', {
  query: { limit: -1 }
})
const { data: tags, refresh: refreshTags } = await useAPI<Tag[]>('/tags')
const { data: tagCategories } = await useAPI<TagCategory[]>('/tag-categories')
const { data: users } = await useAPI<User[]>('/users', {
  query: computed(() => ({
    subject_id: selectedSubjectId.value && selectedSubjectId.value !== '0' ? selectedSubjectId.value : undefined
  }))
})

// Options for Selects
const statusOptions = [
  { label: '全部状态', value: '0' },
  { label: '草稿', value: 'draft' },
  { label: '待审核', value: 'pending' },
  { label: '已发布', value: 'published' },
  { label: '已归档', value: 'archived' },
]

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

const userOptions = computed(() => {
  const opts = [{ label: '全部', value: '0' }]
  if (users.value) {
    opts.push(...users.value.map(u => ({
      label: u.full_name || u.username,
      value: String(u.id)
    })))
  }
  return opts
})

// --- Actions ---
const deleteQuestion = async (id: number) => {
  if (!confirm('确定要删除这道题目吗？')) return
  try {
    await $api(`/questions/${id}`, {
      method: 'DELETE',
    })
    removeFromBasket(id)
    refreshQuestions()
  } catch (error) {
    console.error(error)
  }
}

const createQuestion = () => {
  editingQuestion.value = null
  dialogMode.value = 'create'
  isDialogOpen.value = true
}

const decomposeQuestion = (parent: Question) => {
  // Create a partial question object with parent_id set
  // We cast to any to bypass strict type checking for the partial object
  editingQuestion.value = {
    parent_id: parent.id,
    subject_id: parent.subject_id,
    // Optional: copy tags or other metadata if desired
  } as any
  dialogMode.value = 'create'
  isDialogOpen.value = true
}

const editQuestion = (question: Question) => {
  editingQuestion.value = question
  dialogMode.value = 'edit'
  isDialogOpen.value = true
}

const handleEditSuccess = () => {
  isDialogOpen.value = false
  editingQuestion.value = null
  refreshQuestions()
}

const getKnowledgePointName = (id: number) => {
  return knowledgePoints.value?.find(c => c.id === id)?.name || id
}

// Filter helpers
const filteredKnowledgePoints = computed(() => {
  if (!filters.subject_id || filters.subject_id === '0') return knowledgePoints.value
  return knowledgePoints.value?.filter(c => String(c.subject_id) === filters.subject_id)
})

const resetFilters = () => {
  filters.id = undefined
  
  // If no subject is selected (e.g. coming from ID/Task view), select the first one
  if ((!selectedSubjectId.value || selectedSubjectId.value === '0') && subjects.value && subjects.value.length > 0) {
    selectedSubjectId.value = String(subjects.value[0].id)
  }

  filters.subject_id = selectedSubjectId.value
  filters.knowledge_point_id = undefined
  filters.tag_ids = []
  filters.q_type = undefined
  filters.difficulty = undefined
  filters.status = undefined
  filters.import_task_id = undefined
  filters.import_task_name = undefined
  filters.review_count = undefined
  filters.creator_id = undefined
  filters.reviewer_id = undefined
  filters.keyword = undefined
  filters.source = undefined
  filters.root_only = false
  page.value = 1
  
  // Remove query param
  const query = { ...route.query }
  delete query.import_task_id
  delete query.id
  router.replace({ query })
}

// Watch for query param to open dialog
watch(() => route.query.create, (newVal) => {
  if (newVal === 'true') {
    createQuestion()
  }
}, { immediate: true })

// Clear query param when dialog closes
watch(isDialogOpen, (newVal) => {
  if (!newVal && route.query.create) {
    router.replace({ query: { ...route.query, create: undefined } })
  }
})

const handleQuestionUpdate = (newQuestion: Question) => {
  if (questionPage.value && questionPage.value.items) {
    const index = questionPage.value.items.findIndex(q => q.id === newQuestion.id)
    if (index !== -1) {
      // Create a new array reference to ensure reactivity
      const newItems = [...questionPage.value.items]
      newItems[index] = newQuestion
      
      // Update the page object with the new items array to trigger reactivity
      questionPage.value = {
        ...questionPage.value,
        items: newItems
      }
    }
  }
}

// --- Structure Sheet ---
const structureSheetOpen = ref(false)
const structureQuestionId = ref<number | null>(null)

const viewStructure = (question: Question) => {
  structureQuestionId.value = question.id
  structureSheetOpen.value = true
}
</script>

<template>
  <!-- Header -->
  <PageHeader title="题目管理">
    <template #actions>
      <Button size="sm" @click="createQuestion">
        <Plus class="mr-2 h-4 w-4" />
        创建题目
      </Button>
    </template>
  </PageHeader>
  <div class="flex flex-1 flex-col">
    <div class="@container/main flex flex-1 flex-col px-4 space-y-6 py-6">
      
      <div v-if="filters.import_task_id" class="bg-primary/10 text-primary px-4 py-3 rounded-md flex items-center justify-between">
          <span class="text-sm font-medium">正在查看最新导入的题目任务</span>
          <Button variant="ghost" size="sm" @click="resetFilters" class="h-8 hover:bg-primary/20">
              <X class="mr-2 h-4 w-4" />
              清除筛选
          </Button>
      </div>

      <Tabs v-model="selectedSubjectId" class="w-full">
        <TabsList class="w-full justify-start overflow-x-auto">
          <TabsTrigger v-for="subject in subjects" :key="subject.id" :value="String(subject.id)">
            {{ subject.name }}
          </TabsTrigger>
        </TabsList>

        <TabsContent v-for="subject in subjects" :key="subject.id" :value="String(subject.id)" class="mt-4 space-y-6">
          <div class="flex flex-col md:flex-row gap-6">
            <!-- Mobile Sidebar Toggle -->
            <div class="md:hidden">
              <Sheet>
                <SheetTrigger as-child>
                  <Button variant="outline" class="w-full justify-start">
                    <ListTree class="mr-2 h-4 w-4" />
                    {{ filters.knowledge_point_id ? (getKnowledgePointName(filters.knowledge_point_id as number) || '已选择知识点') : '选择知识点' }}
                  </Button>
                </SheetTrigger>
                <SheetContent side="left" class="w-[300px] sm:w-[400px] p-0">
                  <SheetHeader class="p-4 border-b">
                    <SheetTitle>选择知识点</SheetTitle>
                  </SheetHeader>
                  <div class="h-[calc(100vh-5rem)] overflow-y-auto p-4">
                    <KnowledgePointTreeSelector 
                      :knowledge-points="filteredKnowledgePoints || []" 
                      :selected-id="filters.knowledge_point_id"
                      @select="(id) => filters.knowledge_point_id = id" 
                    />
                  </div>
                </SheetContent>
              </Sheet>
            </div>

            <!-- Desktop Left Sidebar: Knowledge Point Tree -->
            <div class="hidden md:block w-64 flex-shrink-0 border rounded-lg bg-card p-2 h-[calc(100vh-250px)] overflow-y-auto sticky top-4">
              <KnowledgePointTreeSelector :knowledge-points="filteredKnowledgePoints || []" :selected-id="filters.knowledge_point_id"
                @select="(id) => filters.knowledge_point_id = id" />
            </div>

            <!-- Right Content: Filters & Table -->
            <div class="flex-1 space-y-6 min-w-0">
              <!-- Filters -->
              <div class="grid grid-cols-1 gap-4 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 p-4 border rounded-lg bg-card">
              
                <!-- Keyword Filter -->
                <div class="space-y-2 md:col-span-2 lg:col-span-1">
                  <Label class="text-xs font-medium">关键词</Label>
                  <ClearableInput v-model="filters.keyword" placeholder="搜索题目内容..." />
                </div>

                <!-- ID Filter -->
                <div class="space-y-2">
                  <Label class="text-xs font-medium">ID</Label>
                  <ClearableInput v-model="filters.id" placeholder="搜索ID..." />
                </div>

                <!-- Status Filter -->
                <div class="space-y-2">
                  <Label class="text-xs font-medium">状态</Label>
                  <ClearableSelect v-model="filters.status" :options="statusOptions" placeholder="全部状态" />
                </div>

                <!-- Type Filter -->
                <div class="space-y-2">
                  <Label class="text-xs font-medium">题型</Label>
                  <ClearableSelect v-model="filters.q_type" :options="qTypeOptions" placeholder="全部题型" />
                </div>

                <!-- Difficulty Filter -->
                <div class="space-y-2">
                  <Label class="text-xs font-medium">难度</Label>
                  <ClearableSelect v-model="filters.difficulty" :options="difficultyOptions" placeholder="全部难度" />
                </div>

                <!-- Source Filter -->
                <div class="space-y-2">
                  <Label class="text-xs font-medium">来源</Label>
                  <ClearableInput v-model="filters.source" placeholder="搜索来源..." />
                </div>

                <!-- Import Task Name Filter -->
                <div class="space-y-2">
                  <Label class="text-xs font-medium">导入任务</Label>
                  <ClearableInput v-model="filters.import_task_name" placeholder="搜索任务名称..." />
                </div>

                <!-- Review Count Filter -->
                <div class="space-y-2">
                  <Label class="text-xs font-medium">审核次数</Label>
                  <ClearableInput v-model="filters.review_count" type="number" placeholder="次数" />
                </div>

                <!-- Creator Filter -->
                <div class="space-y-2">
                  <Label class="text-xs font-medium">创建人</Label>
                  <ClearableSelect v-model="filters.creator_id" :options="userOptions" placeholder="全部创建人" />
                </div>

                <!-- Reviewer Filter -->
                <div class="space-y-2">
                  <Label class="text-xs font-medium">审核人</Label>
                  <ClearableSelect v-model="filters.reviewer_id" :options="userOptions" placeholder="全部审核人" />
                </div>

                <!-- Tag Filter -->
                <div class="space-y-2 md:col-span-2">
                  <Label class="text-xs font-medium">标签</Label>
                  <TagFilter 
                    v-model="filters.tag_ids" 
                    :tags="tags || []" 
                    :categories="tagCategories || []" 
                  />
                </div>

                <!-- Hierarchy Filter -->
                <!-- <div class="flex items-center space-x-2 pt-6">
                  <Checkbox id="root-only" :checked="filters.root_only" @update:checked="(v) => filters.root_only = v" />
                  <Label for="root-only" class="text-sm font-medium leading-none cursor-pointer">
                    仅显示原题
                  </Label>
                </div> -->

                <!-- Reset Button -->
                <div class="flex items-end">
                  <Button variant="secondary" class="w-full" @click="resetFilters">
                    <X class="mr-2 h-4 w-4" />
                    重置
                  </Button>
                </div>
              </div>

              <!-- Question List -->
              <div class="space-y-4">
                <div class="flex justify-between items-center sticky top-0 z-10 bg-background/95 backdrop-blur py-2 border-b px-2" v-if="questionsStatus !== 'pending'">
                  <div class="flex items-center space-x-2">
                    <Checkbox 
                      id="select-all" 
                      :model-value="isAllPageSelected" 
                      @update:model-value="toggleAllPage" 
                    />
                    <Label for="select-all" class="text-sm font-medium cursor-pointer">全选本页</Label>
                    <Button variant="link" size="sm" class="h-auto p-0 text-muted-foreground" @click="invertSelection">反选</Button>
                    
                    <div v-if="selectedIds.size > 0" class="flex items-center gap-2 ml-4 animate-in fade-in slide-in-from-left-5 duration-300">
                      <span class="text-sm text-muted-foreground">已选 {{ selectedIds.size }} 项</span>
                      <Button size="sm" variant="outline" class="h-7 px-2" @click="batchAddToBasket">
                        <ShoppingBasket class="mr-1 h-3 w-3" />
                        加入试题栏
                      </Button>
                      <Button size="sm" variant="outline" class="h-7 px-2" @click="openBatchUpdateSourceDialog">
                        <Edit class="mr-1 h-3 w-3" />
                        修改来源
                      </Button>
                      <Button size="sm" variant="destructive" class="h-7 px-2" @click="batchDelete">
                        <Trash2 class="mr-1 h-3 w-3" />
                        删除
                      </Button>
                    </div>
                  </div>
                  <div class="flex items-center gap-4">
                    <span class="text-sm text-muted-foreground">共 {{ total }} 道题目</span>
                    <div class="flex items-center gap-2">
                      <span class="text-sm text-muted-foreground">每页</span>
                      <Select :model-value="String(pageSize)" @update:model-value="(v) => pageSize = Number(v)">
                        <SelectTrigger class="h-8 w-[80px]">
                          <SelectValue :placeholder="String(pageSize)" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="10">10</SelectItem>
                          <SelectItem value="20">20</SelectItem>
                          <SelectItem value="50">50</SelectItem>
                          <SelectItem value="100">100</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                </div>
                <div v-if="questionsStatus === 'pending'" class="flex justify-center py-8">
                  <Loader2 class="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
                <div v-else-if="questions.length === 0" class="text-center py-8 text-muted-foreground">
                  暂无数据
                </div>
                <div v-else class="space-y-4">
                  <QuestionListItem 
                    v-for="question in questions" 
                    :key="question.id"
                    :item="question"
                    mode="library"
                    selectable
                    :selected="selectedIds.has(question.id)"
                    @select="(v) => handleSelect(question.id, v)"
                    @edit="editQuestion(question)"
                    @delete="deleteQuestion(question.id)"
                    @update="handleQuestionUpdate"
                    @view-structure="viewStructure"
                    @decompose="decomposeQuestion"
                  />
                </div>

                <!-- Pagination -->
                <div v-if="total > 0" class="flex justify-center mt-4 pb-8">
                  <Pagination v-model:page="page" :total="total" :sibling-count="1" show-edges :default-page="1"
                    :items-per-page="pageSize">
                    <PaginationContent v-slot="{ items }" class="flex items-center gap-1">
                      <PaginationFirst />
                      <PaginationPrevious />
                      <template v-for="(item, index) in items">
                        <PaginationItem v-if="item.type === 'page'" :key="index" :value="item.value" as-child>
                          <Button class="w-10 h-10 p-0" :variant="item.value === page ? 'default' : 'outline'">
                            {{ item.value }}
                          </Button>
                        </PaginationItem>
                        <PaginationEllipsis v-else :key="item.type" :index="index" />
                      </template>
                      <PaginationNext />
                      <PaginationLast />
                    </PaginationContent>
                  </Pagination>
                </div>
              </div>
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  </div>

  <!-- Edit Dialog -->
  <QuestionEditDialog
    :open="isDialogOpen"
    :question="editingQuestion"
    :knowledge-points="knowledgePoints"
    :subjects="subjects"
    :mode="dialogMode"
    @update:open="(v) => isDialogOpen = v"
    @success="handleEditSuccess"
  />
  
  <QuestionStructureSheet
    v-model:open="structureSheetOpen"
    :question-id="structureQuestionId"
  />
  
  <Dialog :open="isSourceDialogOpen" @update:open="(v) => isSourceDialogOpen = v">
    <DialogContent class="sm:max-w-[425px]">
      <DialogHeader>
        <DialogTitle>批量修改来源</DialogTitle>
        <DialogDescription>
          请输入新的来源名称。这将更新选中的 {{ selectedIds.size }} 道题目。
        </DialogDescription>
      </DialogHeader>
      <div class="grid gap-4 py-4">
        <div class="grid grid-cols-4 items-center gap-4">
          <Label for="source" class="text-right">
            来源
          </Label>
          <Input
            id="source"
            v-model="newSourceValue"
            class="col-span-3"
            placeholder="例如：2024年期末考试"
          />
        </div>
      </div>
      <DialogFooter>
        <Button type="submit" @click="batchUpdateSource">保存更改</Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>

  <PaperBasket />
</template>
