<script setup lang="ts">
import { computed, ref } from 'vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Card } from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Pencil, Trash2, Copy, ChevronDown, Star, ShoppingBasket, CheckCircle, History, Workflow, CornerDownRight, GitFork, FileText, AlertTriangle, MoreVertical } from '@lucide/vue'
import MarkdownPreview from './MarkdownPreview.vue'
import RichContent from './rich-editor/RichContent.vue'
import AnswerDisplay from './AnswerDisplay.vue'
import { isEmptyRichDoc, richDocToPlainText } from './rich-editor/richDoc'
import CompositionQuickAdd from './CompositionQuickAdd.vue'
import { useQuestionBasket } from '@/composables/useQuestionBasket'
import type { Question as DbQuestion, KnowledgePoint, ImportItem, OptionSpec } from '@/types'
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
  hideDelete?: boolean
  hideDecompose?: boolean
  defaultExpanded?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  mode: 'import',
  index: 0,
  allKnowledgePoints: () => [],
  selected: false,
  selectable: false,
  hideDelete: false,
  hideDecompose: false,
  defaultExpanded: false
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
    // 只表达审核意图，是否达到发布所需审核次数由后端依据科目配置判定。
    const data = await $api<DbQuestion>(`/questions/${props.item.id}/review`, {
      method: 'POST',
      body: { action: 'approve', comment: 'Approved via quick review' }
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

// Kept intentionally low-saturation so type colors don't compete with the primary theme color.
const typeColor = computed(() => {
  const colors: Record<string, string> = {
    'single_choice': 'bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400',
    'multiple_choice': 'bg-violet-50 text-violet-700 dark:bg-violet-500/10 dark:text-violet-400',
    'true_false': 'bg-teal-50 text-teal-700 dark:bg-teal-500/10 dark:text-teal-400',
    'fill_in_the_blank': 'bg-orange-50 text-orange-700 dark:bg-orange-500/10 dark:text-orange-400',
    'free_response': 'bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400'
  }
  return colors[props.item.q_type] || 'bg-muted text-muted-foreground'
})

const warnings = computed<string[]>(() => {
  if (props.mode !== 'import') return []
  const w = (props.item as ImportItem).warnings
  return Array.isArray(w) ? w : []
})

// import 模式题干是 Markdown 字符串，截断做摘要预览。
const contentPreview = computed(() => {
  const raw = (props.item as ImportItem).content || ''
  const text = raw
    .replace(/<[^>]*>/g, '')
    .replace(/[\n\r]+/g, ' ')
    .substring(0, 100)
  return text + (raw.length > 100 ? '...' : '')
})

const difficultyLabel = computed(() => {
  return `难度 ${props.item.difficulty}`
})

const basket = useQuestionBasket()
const inBasket = computed(() => basket.has(Number(props.item.id)))
const toggleBasket = () => {
  const q = props.item as DbQuestion
  const wasInBasket = inBasket.value
  basket.toggle({
    id: Number(q.id),
    subject_id: q.subject_id ?? 0,
    content_preview: richDocToPlainText(q.content).slice(0, 40),
    q_type: q.q_type,
    difficulty: q.difficulty,
  })
  toast.success(wasInBasket ? '已移出试题篮' : '已加入试题篮')
}

const expanded = ref(props.defaultExpanded)

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
      return { variant: 'default' as const, class: 'bg-green-600 hover:bg-green-700 dark:bg-green-700 dark:hover:bg-green-600' }
    case 'pending':
      return { variant: 'secondary' as const, class: 'bg-amber-100 text-amber-800 hover:bg-amber-200 dark:bg-amber-500/15 dark:text-amber-400 dark:hover:bg-amber-500/25' }
    case 'draft':
      return { variant: 'secondary' as const, class: '' }
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

const dbOptions = computed<OptionSpec[]>(() => (props.item as DbQuestion).options || [])
const importOptions = computed(() => (props.item as ImportItem).options || [])

const knowledgePointIds = computed(() => {
  const item = props.item as ImportItem
  return item.knowledge_point_ids || []
})

// 仅 import 模式：旧填空答案可能是 JSON 数组字符串，解析用于展示。
const parsedAnswer = computed(() => {
  if (props.mode !== 'import' || props.item.q_type !== 'fill_in_the_blank') return null
  const ans = (props.item as ImportItem).answer
  try {
    if (typeof ans === 'string' && ans.trim().startsWith('[')) {
      return JSON.parse(ans)
    }
    return []
  } catch (e) {
    return []
  }
})

const isChecked = computed({
  get: () => props.selected,
  set: (val) => emit('select', val as boolean)
})

// Left accent border so status is scannable without reading the badge text
const statusAccentClass = computed(() => {
  const item = props.item as DbQuestion
  switch (item.status) {
    case 'published':
      return 'border-l-green-600 dark:border-l-green-600'
    case 'pending':
      return 'border-l-amber-400 dark:border-l-amber-500'
    case 'archived':
      return 'border-l-muted-foreground/25'
    case 'draft':
    default:
      return 'border-l-muted-foreground/40'
  }
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
  <Card
    class="py-0 transition-colors hover:border-foreground/20"
    :class="[{ 'opacity-60': !isSelected }, mode === 'library' ? ['border-l-4', statusAccentClass] : '']"
  >
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
              <Badge v-if="(item as DbQuestion).status" :variant="statusBadgeProps.variant" :class="['text-xs', statusBadgeProps.class]">
                {{ statusLabel }}
              </Badge>
              <Badge variant="outline">{{ typeLabel }}</Badge>

              <!-- Structure Badges -->
              <Badge v-if="(item as DbQuestion).parent_id" variant="secondary" class="flex items-center gap-1 px-1.5 bg-indigo-50 text-indigo-700 hover:bg-indigo-100 dark:bg-indigo-500/10 dark:text-indigo-400">
                 子题
              </Badge>
              <Badge v-if="(item as DbQuestion).children?.length" variant="secondary" class="flex items-center gap-1 px-1.5 bg-blue-50 text-blue-700 hover:bg-blue-100 dark:bg-blue-500/10 dark:text-blue-400">
                 母题
              </Badge>

              <!-- Fixed 5-star scale so difficulty is comparable at a glance across items -->
              <div class="flex items-center gap-1" :title="difficultyLabel">
                <span class="text-xs text-muted-foreground">难度</span>
                <Star v-for="i in 5" :key="i"
                  class="h-3 w-3"
                  :class="i <= item.difficulty ? 'fill-primary text-primary' : 'fill-none text-muted-foreground/30'" />
              </div>

              <span 
                class="text-xs font-mono text-muted-foreground bg-muted px-1.5 py-0.5 rounded cursor-pointer hover:bg-accent hover:text-accent-foreground transition-colors"
                title="点击复制 ID"
                @click="copyId(item.id)"
              >ID: {{ item.id }}</span>
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
              class="h-8 w-8 text-green-600 hover:text-green-700 hover:bg-green-50 dark:hover:bg-green-500/10"
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
              class="h-8 w-8"
              :class="inBasket ? 'text-primary' : 'text-muted-foreground'"
              :title="inBasket ? '移出试题篮' : '加入试题篮'"
              @click="toggleBasket"
            >
              <ShoppingBasket class="h-4 w-4" />
            </Button>

            <CompositionQuickAdd
              v-if="mode === 'library'"
              :question-id="Number(item.id)"
              :subject-id="(item as DbQuestion).subject_id ?? null"
            />

            <!-- Low-frequency reference action: kept before the overflow menu, after the higher-frequency edit/review/basket/compose actions -->
            <Button
              v-if="sourceFileUrl"
              as-child
              variant="ghost"
              size="icon"
              class="h-8 w-8 text-muted-foreground"
              title="查看源文件"
            >
              <NuxtLink :to="{ path: '/preview', query: { url: sourceFileUrl } }" target="_blank">
                <FileText class="h-4 w-4" />
              </NuxtLink>
            </Button>

            <!-- Lower-frequency/destructive actions grouped to reduce icon clutter -->
            <DropdownMenu v-if="mode === 'library'">
              <DropdownMenuTrigger as-child>
                <Button variant="ghost" size="icon" class="h-8 w-8" title="更多操作">
                  <MoreVertical class="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem
                  v-if="!hideDecompose"
                  @click="emit('decompose', item as DbQuestion)"
                >
                  <GitFork class="h-4 w-4" />
                  添加子题
                </DropdownMenuItem>
                <DropdownMenuItem
                  v-if="(item as DbQuestion).children?.length || (item as DbQuestion).parent_id"
                  @click="emit('view-structure', item as DbQuestion)"
                >
                  <Workflow class="h-4 w-4" />
                  查看结构图谱
                </DropdownMenuItem>
                <DropdownMenuItem
                  v-if="!hideDelete"
                  variant="destructive"
                  @click="emit('delete')"
                >
                  <Trash2 class="h-4 w-4" />
                  删除
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>

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
              v-if="!hideDelete && mode !== 'library'"
              variant="ghost"
              size="icon"
              class="h-8 w-8 text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-500/10"
              title="删除"
              @click="emit('delete')"
            >
              <Trash2 class="h-4 w-4" />
            </Button>
            

          </div>
        </div>

        <!-- Content -->
        <div class="w-full">
          <div v-if="warnings.length > 0" class="mb-2 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-700 dark:bg-amber-900/20 dark:text-amber-300">
            <div v-for="(w, wi) in warnings" :key="wi" class="flex items-center gap-1.5">
              <AlertTriangle class="h-3.5 w-3.5 shrink-0" />
              <span>{{ w }}</span>
            </div>
          </div>
          <div v-if="mode === 'library'" class="prose prose-sm max-w-none dark:prose-invert">
            <RichContent :content="(item as DbQuestion).content" empty-text="（空）" />
          </div>
          <div v-else class="text-sm text-muted-foreground mb-2">
            <MarkdownPreview :content="contentPreview" />
          </div>
          
          <!-- Options for choice questions -->
          <div v-if="mode === 'library' && dbOptions.length > 0 && (item.q_type === 'single_choice' || item.q_type === 'multiple_choice')" class="mt-2 mb-3 flex flex-wrap gap-x-6 gap-y-1.5">
            <div v-for="opt in dbOptions" :key="opt.id" class="flex max-w-full gap-2 items-baseline text-xs">
              <span class="font-bold text-muted-foreground shrink-0">{{ opt.label }}.</span>
              <div class="min-w-0 text-foreground/80 [&_.prose]:my-0 [&_.prose_p]:my-0 [&_.prose]:text-xs [&_.prose]:leading-normal">
                <RichContent :content="opt.content" />
              </div>
            </div>
          </div>
          <div v-else-if="mode !== 'library' && importOptions.length > 0 && (item.q_type === 'single_choice' || item.q_type === 'multiple_choice')" class="mt-2 mb-3 flex flex-wrap gap-x-6 gap-y-1.5">
            <div v-for="(opt, oi) in importOptions" :key="oi" class="flex max-w-full gap-2 items-baseline text-xs">
              <span class="font-bold text-muted-foreground shrink-0">{{ opt.label }}.</span>
              <div class="min-w-0 text-foreground/80 [&_.prose]:my-0 [&_.prose_p]:my-0 [&_.prose]:text-xs [&_.prose]:leading-normal">
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

        <!-- Expand Button: also gates the metadata footer below, so the card stays compact by default -->
        <div v-if="mode === 'import' || mode === 'library'" class="flex justify-center">
          <Button
            variant="ghost"
            size="sm"
            class="h-6 w-full gap-1 text-muted-foreground hover:bg-muted/50"
            @click="expanded = !expanded"
          >
            <span class="text-xs">{{ expanded ? '收起详情' : '展开详情' }}</span>
            <ChevronDown class="h-4 w-4 transition-transform duration-200" :class="{ 'rotate-180': expanded }" />
          </Button>
        </div>
      </div>

      <!-- Expandable Details (import mode) -->
      <div v-if="mode === 'import' && expanded" class="mt-4 pt-4 border-t border-border/50 space-y-4">
        <div class="space-y-2">
          <div class="text-sm font-semibold text-foreground">答案</div>
          <div class="text-sm bg-muted/30 p-2 rounded">
            <div v-if="item.q_type === 'fill_in_the_blank' && parsedAnswer && parsedAnswer.length > 0" class="flex flex-col gap-2">
              <div v-for="(blank, index) in parsedAnswer" :key="index" class="flex items-start gap-2">
                <span v-if="parsedAnswer.length > 1" class="font-mono text-muted-foreground shrink-0 mt-1.5">{{ Number(index) + 1 }}.</span>
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
          <div class="text-sm font-semibold text-foreground">分析</div>
          <div class="text-sm bg-muted/20 p-3 rounded [&_.prose]:my-0 [&_.prose>p]:my-0">
            <MarkdownPreview :content="(item as ImportItem).thinking || ''" />
          </div>
        </div>

        <div v-if="(item as ImportItem).analysis" class="space-y-2">
          <div class="text-sm font-semibold text-foreground">解析</div>
          <div class="text-sm bg-muted/20 p-3 rounded [&_.prose]:my-0 [&_.prose>p]:my-0">
            <MarkdownPreview :content="(item as ImportItem).analysis || ''" />
          </div>
        </div>
      </div>

      <!-- Expandable Details (library mode) -->
      <div v-if="mode === 'library' && expanded" class="mt-4 pt-4 border-t border-border/50 space-y-4">
        <div class="space-y-2">
          <div class="text-sm font-semibold text-foreground">答案</div>
          <div class="text-sm bg-muted/30 p-2 rounded">
            <AnswerDisplay :answer="(item as DbQuestion).answer" :options="(item as DbQuestion).options" />
          </div>
        </div>

        <div v-if="!isEmptyRichDoc((item as DbQuestion).thinking)" class="space-y-2">
          <div class="text-sm font-semibold text-foreground">分析</div>
          <div class="text-sm bg-muted/20 p-3 rounded [&_.prose]:my-0 [&_.prose_p]:my-0">
            <RichContent :content="(item as DbQuestion).thinking" />
          </div>
        </div>

        <div v-if="!isEmptyRichDoc((item as DbQuestion).analysis)" class="space-y-2">
          <div class="text-sm font-semibold text-foreground">解析</div>
          <div class="text-sm bg-muted/20 p-3 rounded [&_.prose]:my-0 [&_.prose_p]:my-0">
            <RichContent :content="(item as DbQuestion).analysis" />
          </div>
        </div>

        <div v-if="!isEmptyRichDoc((item as DbQuestion).summary)" class="space-y-2">
          <div class="text-sm font-semibold text-foreground">总结</div>
          <div class="text-sm bg-muted/20 p-3 rounded [&_.prose]:my-0 [&_.prose_p]:my-0">
            <RichContent :content="(item as DbQuestion).summary" />
          </div>
        </div>

        <!-- Audit metadata: secondary info, pushed to the footer so answer/analysis surface first -->
        <div class="text-xs text-muted-foreground flex flex-col gap-1.5 pt-3 border-t border-border/50">
          <div class="flex flex-wrap gap-x-6 gap-y-1">
            <div>
              <span class="font-medium">创建:</span> {{ (item as DbQuestion).creator?.full_name || (item as DbQuestion).creator?.username || 'Unknown' }}
              <span class="ml-1">{{ new Date((item as DbQuestion).created_at + 'Z').toLocaleString() }}</span>
            </div>
            <div>
              <span class="font-medium">更新:</span> {{ (item as DbQuestion).updater?.full_name || (item as DbQuestion).updater?.username || 'Unknown' }}
              <span class="ml-1">{{ new Date((item as DbQuestion).updated_at + 'Z').toLocaleString() }}</span>
            </div>
          </div>
          <div class="flex flex-col gap-1">
            <div class="flex items-center gap-2">
              <span class="font-medium">审核次数:</span> {{ (item as DbQuestion).review_count }}
            </div>
            <div v-if="(item as DbQuestion).review_logs?.length" class="flex gap-1 flex-wrap mt-1">
               <span v-for="log in (item as DbQuestion).review_logs" :key="log.id" class="bg-muted px-2 py-0.5 rounded text-[10px] flex items-center gap-1">
                  <History class="w-3 h-3" />
                  {{ log.user?.full_name || log.user?.username }} ({{ new Date(log.created_at + 'Z').toLocaleDateString() }})
               </span>
            </div>
          </div>
          <div v-if="(item as DbQuestion).source">
            <span class="font-medium">来源:</span> {{ (item as DbQuestion).source }}
          </div>
        </div>
      </div>
    </div>
  </Card>
</template>
