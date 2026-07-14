<script setup lang="ts">
import { computed, ref } from 'vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Card } from '@/components/ui/card'
import { Pencil, Trash2, Copy, ChevronDown, Star, ShoppingBasket, CheckCircle, History, Workflow, CornerDownRight, GitFork, FileText } from 'lucide-vue-next'
import MarkdownPreview from './MarkdownPreview.vue'
import type { Question as DbQuestion, KnowledgePoint, ImportItem } from '@/types'
import { usePaperBasket } from '@/composables/usePaperBasket'
import { toast } from 'vue-sonner'

// Support both import items and database questions
interface BaseItem {
    id: string | number
    content: string
    q_type: string
    difficulty: number
}

interface Props {
  item: ImportItem | DbQuestion
  index?: number
  mode?: 'import' | 'library'
  allKnowledgePoints?: KnowledgePoint[]
  selected?: boolean
  selectable?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  mode: 'import',
  index: 0,
  allKnowledgePoints: () => [],
  selected: false,
  selectable: false
})

const emit = defineEmits<{
  (e: 'edit'): void
  (e: 'delete'): void
  (e: 'duplicate'): void
  (e: 'refresh'): void
  (e: 'update', item: DbQuestion): void
  (e: 'view-structure', item: DbQuestion): void
  (e: 'decompose', item: DbQuestion): void
  (e: 'select', val: boolean): void
}>()

const { $api } = useNuxtApp()

const isReviewing = ref(false)
const handleReview = async () => {
  if (props.mode !== 'library') return
  isReviewing.value = true
  try {
    const data = await $api<DbQuestion>(`/questions/${props.item.id}/review`, {
      method: 'POST',
      body: { status: 'published', comment: 'Approved via quick review' }
    })
    emit('update', data)
  } catch (e) {
    console.error('Review exception:', e)
  } finally {
    isReviewing.value = false
  }
}

const typeLabel = computed(() => {
  const types: Record<string, string> = {
    'single_choice': '单选题',
    'multiple_choice': '多选题',
    'true_false': '判断题',
    'fill_in_the_blank': '填空题',
    'free_response': '解答题'
  }
  return types[props.item.q_type] || props.item.q_type
})

const typeColor = computed(() => {
  const colors: Record<string, string> = {
    'single_choice': 'bg-blue-100 text-blue-800',
    'multiple_choice': 'bg-purple-100 text-purple-800',
    'true_false': 'bg-green-100 text-green-800',
    'fill_in_the_blank': 'bg-orange-100 text-orange-800',
    'free_response': 'bg-yellow-100 text-yellow-800'
  }
  return colors[props.item.q_type] || 'bg-gray-100 text-gray-800'
})

const contentPreview = computed(() => {
  if (props.mode === 'library') {
    return props.item.content
  }
  const text = props.item.content
    .replace(/<[^>]*>/g, '')
    .replace(/[\n\r]+/g, ' ')
    .substring(0, 100)
  return text + (props.item.content.length > 100 ? '...' : '')
})

const difficultyLabel = computed(() => {
  return `难度 ${props.item.difficulty}`
})

const expanded = ref(false)

const statusLabel = computed(() => {
  const item = props.item as DbQuestion
  if (item.status === 'published') return '已发布'
  if (item.status === 'draft') return '草稿'
  if (item.status === 'pending') {
    if (item.subject?.required_review_count && item.subject.required_review_count > 1) {
      return `待审核 (${item.review_count || 0}/${item.subject.required_review_count})`
    }
    return '待审核'
  }
  if (item.status === 'archived') return '已归档'
  return item.status
})

const statusBadgeProps = computed(() => {
  const item = props.item as DbQuestion
  switch (item.status) {
    case 'published':
      return { variant: 'default' as const, class: 'bg-green-600 hover:bg-green-700' }
    case 'pending':
      return { variant: 'secondary' as const, class: 'bg-yellow-100 text-yellow-800 hover:bg-yellow-200' }
    case 'draft':
      return { variant: 'secondary' as const, class: 'bg-gray-100 text-gray-800 hover:bg-gray-200' }
    case 'archived':
      return { variant: 'outline' as const, class: 'text-muted-foreground' }
    default:
      return { variant: 'secondary' as const, class: '' }
  }
})

const isSelected = computed(() => {
  const item = props.item as ImportItem
  return item.selected !== false
})

const knowledgePoints = computed(() => {
  const item = props.item as DbQuestion
  return item.knowledge_points || []
})

const tags = computed(() => {
  const item = props.item as DbQuestion
  return item.tags || []
})

const options = computed(() => {
  return props.item.options || []
})

const { has, toggle } = usePaperBasket()
const isInBasket = computed(() => has(Number(props.item.id)))

const knowledgePointIds = computed(() => {
  const item = props.item as ImportItem
  return item.knowledge_point_ids || []
})

const parsedAnswer = computed(() => {
  if (props.item.q_type !== 'fill_in_the_blank') return null
  try {
    const ans = props.item.answer
    if (typeof ans === 'string') {
      // Check if it looks like JSON array
      if (ans.trim().startsWith('[')) {
         return JSON.parse(ans)
      }
      return []
    }
    return Array.isArray(ans) ? ans : []
  } catch (e) {
    return []
  }
})

const isChecked = computed({
  get: () => props.selected,
  set: (val) => emit('select', val as boolean)
})

const copyId = (id: string | number) => {
  navigator.clipboard.writeText(String(id))
  toast.success('ID 已复制')
}

const sourceFileUrl = computed(() => {
  const item = props.item as DbQuestion
  if (item.import_task?.file_path) {
    return `/${item.import_task.file_path}`
  }
  return null
})
</script>

<template>
  <Card class="hover:shadow-md transition-shadow py-0" :class="{ 'opacity-60': !isSelected }">
    <div class="p-4">
      <div class="flex flex-col gap-3">
        <!-- Header: Meta & Actions -->
        <div class="flex justify-between items-start">
          <!-- Meta Info -->
          <div class="flex gap-3 items-center flex-wrap">
            <Checkbox v-if="selectable" v-model="isChecked" />
            <!-- Index & Type Badge (import mode only) -->
            <div v-if="mode === 'import'" class="flex gap-2 items-center">
              <Badge variant="outline">{{ index + 1 }}</Badge>
              <Badge :class="typeColor" class="text-xs">{{ typeLabel }}</Badge>
            </div>

            <!-- Type & Status (library mode) -->
            <div v-else class="flex gap-2 items-center flex-wrap">
              <span 
                class="text-xs font-mono text-muted-foreground bg-muted px-1.5 py-0.5 rounded cursor-pointer hover:bg-accent hover:text-accent-foreground transition-colors"
                title="点击复制 ID"
                @click="copyId(item.id)"
              >ID: {{ item.id }}</span>
              <Badge variant="outline">{{ typeLabel }}</Badge>
              
              <!-- Structure Badges -->
              <Badge v-if="(item as DbQuestion).parent_id" variant="secondary" class="flex items-center gap-1 px-1.5 bg-indigo-100 text-indigo-800 hover:bg-indigo-200">
                 子题
              </Badge>
              <Badge v-if="(item as DbQuestion).children?.length" variant="secondary" class="flex items-center gap-1 px-1.5 bg-blue-100 text-blue-800 hover:bg-blue-200">
                 母题
              </Badge>

              <div class="flex">
                <Star v-for="i in item.difficulty" :key="i"
                  class="h-3 w-3 fill-yellow-400 text-yellow-400" />
              </div>
              <Badge v-if="(item as DbQuestion).status" :variant="statusBadgeProps.variant" :class="['text-xs', statusBadgeProps.class]">
                {{ statusLabel }}
              </Badge>

              <NuxtLink 
                v-if="sourceFileUrl" 
                :to="{ path: '/preview', query: { url: sourceFileUrl } }" 
                target="_blank" 
                class="flex items-center gap-1 text-xs text-muted-foreground hover:text-primary hover:underline ml-2"
                title="查看源文件"
              >
                <FileText class="h-3 w-3" />
                源文件
              </NuxtLink>
            </div>
          </div>

          <!-- Actions -->
          <div class="flex gap-1">

            <Button
              variant="ghost"
              size="icon"
              class="h-8 w-8"
              title="编辑"
              @click="emit('edit')"
            >
              <Pencil class="h-4 w-4" />
            </Button>

            <Button
              v-if="mode === 'library' && (item as DbQuestion).status === 'pending'"
              variant="ghost"
              size="icon"
              class="h-8 w-8 text-green-600 hover:text-green-700 hover:bg-green-50"
              title="通过审核"
              @click.stop="handleReview"
              :disabled="isReviewing"
            >
              <CheckCircle class="h-4 w-4" />
            </Button>

            <Button
              v-if="mode === 'library'"
              variant="ghost"
              size="icon"
              class="h-8 w-8 text-indigo-600 hover:text-indigo-700 hover:bg-indigo-50"
              title="添加子题"
              @click="emit('decompose', item as DbQuestion)"
            >
              <GitFork class="h-4 w-4" />
            </Button>

            <Button
              v-if="mode === 'library' && ((item as DbQuestion).children?.length || (item as DbQuestion).parent_id)"
              variant="ghost"
              size="icon"
              class="h-8 w-8 text-blue-600 hover:text-blue-700 hover:bg-blue-50"
              title="查看结构图谱"
              @click="emit('view-structure', item as DbQuestion)"
            >
              <Workflow class="h-4 w-4" />
            </Button>
            
            <Button
              v-if="mode === 'library'"
              variant="ghost"
              size="icon"
              class="h-8 w-8"
              :class="isInBasket ? 'text-primary bg-primary/10' : 'text-muted-foreground'"
              @click="toggle({ id: Number(item.id), content: item.content, q_type: item.q_type })"
              title="加入试题篮"
            >
              <ShoppingBasket class="h-4 w-4" />
            </Button>

            <Button
              v-if="mode === 'import'"
              variant="ghost"
              size="icon"
              class="h-8 w-8"
              title="复制"
              @click="emit('duplicate')"
            >
              <Copy class="h-4 w-4" />
            </Button>
            
            <Button
              variant="ghost"
              size="icon"
              class="h-8 w-8 text-red-600 hover:text-red-700 hover:bg-red-50"
              title="删除"
              @click="emit('delete')"
            >
              <Trash2 class="h-4 w-4" />
            </Button>
            

          </div>
        </div>

        <!-- Content -->
        <div class="w-full">
          <div :class="mode === 'library' ? 'prose prose-sm max-w-none dark:prose-invert' : 'text-sm text-gray-600 mb-2'">
            <MarkdownPreview :content="contentPreview" />
          </div>
          
          <!-- Options for choice questions -->
          <div v-if="options.length > 0 && (item.q_type === 'single_choice' || item.q_type === 'multiple_choice')" class="mt-2 mb-3 space-y-1">
            <div v-for="opt in options" :key="opt.label" class="flex gap-2 text-xs">
              <span class="font-bold text-gray-600 shrink-0">{{ opt.label }}.</span>
              <div class="flex-1 text-gray-700 [&_.prose]:my-0 [&_.prose>p]:my-0 [&_.prose]:text-xs">
                <MarkdownPreview :content="opt.content" />
              </div>
            </div>
          </div>

          <!-- Knowledge Points & Tags (library mode) -->
          <div v-if="mode === 'library' && (knowledgePoints.length > 0 || tags.length > 0)" class="mt-4 flex flex-wrap gap-2">
            <Badge v-for="kp in knowledgePoints" :key="kp.id" variant="secondary" class="text-xs">
              {{ kp.name }}
            </Badge>
            <Badge 
              v-for="tag in tags" 
              :key="tag.id" 
              variant="outline" 
              class="text-xs"
              :style="{ borderColor: tag.color, color: tag.color }"
            >
              {{ tag.name }}
            </Badge>
          </div>

          <!-- Metadata Footer (library mode) -->
          <div v-if="mode === 'library'" class="mt-4 pt-4 border-t text-xs text-muted-foreground grid grid-cols-1 sm:grid-cols-2 gap-2">
            <div>
              <span class="font-medium">创建:</span> {{ (item as DbQuestion).creator?.full_name || (item as DbQuestion).creator?.username || 'Unknown' }} 
              <span class="ml-1">{{ new Date((item as DbQuestion).created_at + 'Z').toLocaleString() }}</span>
            </div>
            <div>
              <span class="font-medium">更新:</span> {{ (item as DbQuestion).updater?.full_name || (item as DbQuestion).updater?.username || 'Unknown' }}
              <span class="ml-1">{{ new Date((item as DbQuestion).updated_at + 'Z').toLocaleString() }}</span>
            </div>
            <div class="col-span-1 sm:col-span-2 flex flex-col gap-1">
              <div class="flex items-center gap-2">
                <span class="font-medium">审核次数:</span> {{ (item as DbQuestion).review_count }}
              </div>
              <div v-if="(item as DbQuestion).review_logs?.length" class="flex gap-1 flex-wrap mt-1">
                 <span v-for="log in (item as DbQuestion).review_logs" :key="log.id" class="bg-gray-100 px-2 py-0.5 rounded text-[10px] flex items-center gap-1">
                    <History class="w-3 h-3" />
                    {{ log.user?.full_name || log.user?.username }} ({{ new Date(log.created_at + 'Z').toLocaleDateString() }})
                 </span>
              </div>
            </div>
            <div v-if="(item as DbQuestion).source" class="col-span-1 sm:col-span-2">
              <span class="font-medium">来源:</span> {{ (item as DbQuestion).source }}
            </div>
          </div>

          <!-- Info badges (import mode) -->
          <div v-if="mode === 'import'" class="flex gap-2 flex-wrap">
            <Badge variant="secondary" class="text-xs">{{ difficultyLabel }}</Badge>
            <template v-if="knowledgePointIds.length > 0">
               <template v-if="allKnowledgePoints && allKnowledgePoints.length > 0">
                  <Badge v-for="id in knowledgePointIds" :key="id" variant="secondary" class="text-xs">
                    {{ allKnowledgePoints.find(kp => kp.id === id)?.name || id }}
                  </Badge>
               </template>
               <Badge v-else variant="secondary" class="text-xs">
                  {{ knowledgePointIds.length }} 个知识点
               </Badge>
            </template>
            <Badge v-else variant="outline" class="text-xs text-orange-600">未选择知识点</Badge>
          </div>
        </div>

        <!-- Expand Button -->
        <div v-if="mode === 'import' || (mode === 'library' && ((item as DbQuestion).answer || (item as DbQuestion).thinking || (item as DbQuestion).analysis || (item as DbQuestion).summary))" class="flex justify-center">
          <Button
            variant="ghost"
            size="sm"
            class="h-6 w-full text-muted-foreground hover:bg-muted/50"
            @click="expanded = !expanded"
          >
            <ChevronDown class="h-4 w-4 transition-transform duration-200" :class="{ 'rotate-180': expanded }" />
          </Button>
        </div>
      </div>

      <!-- Expandable Details (import mode) -->
      <div v-if="mode === 'import' && expanded" class="mt-4 pt-4 border-t border-border/50 space-y-4">
        <div class="space-y-2">
          <div class="text-sm font-semibold text-gray-700">答案</div>
          <div class="text-sm bg-muted/30 p-2 rounded">
            <div v-if="item.q_type === 'fill_in_the_blank' && parsedAnswer && parsedAnswer.length > 0" class="flex flex-col gap-2">
              <div v-for="(blank, index) in parsedAnswer" :key="index" class="flex items-start gap-2">
                <span v-if="parsedAnswer.length > 1" class="font-mono text-gray-500 shrink-0 mt-1.5">{{ Number(index) + 1 }}.</span>
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
            <MarkdownPreview v-else :content="(item as ImportItem).answer || '未填写'" />
          </div>
        </div>

        <div v-if="(item as ImportItem).thinking" class="space-y-2">
          <div class="text-sm font-semibold text-gray-700">分析</div>
          <div class="text-sm bg-muted/20 p-3 rounded [&_.prose]:my-0 [&_.prose>p]:my-0">
            <MarkdownPreview :content="(item as ImportItem).thinking || ''" />
          </div>
        </div>

        <div v-if="(item as ImportItem).analysis" class="space-y-2">
          <div class="text-sm font-semibold text-gray-700">解析</div>
          <div class="text-sm bg-muted/20 p-3 rounded [&_.prose]:my-0 [&_.prose>p]:my-0">
            <MarkdownPreview :content="(item as ImportItem).analysis || ''" />
          </div>
        </div>
      </div>

      <!-- Expandable Details (library mode) -->
      <div v-if="mode === 'library' && expanded" class="mt-4 pt-4 border-t border-border/50 space-y-4">
        <div class="space-y-2">
          <div class="text-sm font-semibold text-gray-700">答案</div>
          <div class="text-sm bg-muted/30 p-2 rounded">
            <div v-if="item.q_type === 'fill_in_the_blank' && parsedAnswer && parsedAnswer.length > 0" class="flex flex-col gap-2">
              <div v-for="(blank, index) in parsedAnswer" :key="index" class="flex items-start gap-2">
                <span v-if="parsedAnswer.length > 1" class="font-mono text-gray-500 shrink-0 mt-1.5">{{ Number(index) + 1 }}.</span>
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
            <MarkdownPreview v-else :content="(item as DbQuestion).answer || '未填写'" />
          </div>
        </div>

        <div v-if="(item as DbQuestion).thinking" class="space-y-2">
          <div class="text-sm font-semibold text-gray-700">分析</div>
          <div class="text-sm bg-muted/20 p-3 rounded [&_.prose]:my-0 [&_.prose>p]:my-0">
            <MarkdownPreview :content="(item as DbQuestion).thinking || ''" />
          </div>
        </div>

        <div v-if="(item as DbQuestion).analysis" class="space-y-2">
          <div class="text-sm font-semibold text-gray-700">解析</div>
          <div class="text-sm bg-muted/20 p-3 rounded [&_.prose]:my-0 [&_.prose>p]:my-0">
            <MarkdownPreview :content="(item as DbQuestion).analysis || ''" />
          </div>
        </div>

        <div v-if="(item as DbQuestion).summary" class="space-y-2">
          <div class="text-sm font-semibold text-gray-700">总结</div>
          <div class="text-sm bg-muted/20 p-3 rounded [&_.prose]:my-0 [&_.prose>p]:my-0">
            <MarkdownPreview :content="(item as DbQuestion).summary || ''" />
          </div>
        </div>
      </div>
    </div>
  </Card>
</template>
