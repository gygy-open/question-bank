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
import { Pencil, Trash2, Copy, ChevronDown, Star, ShoppingBasket, CheckCircle, History, Workflow, CornerDownRight, GitFork, FileText, AlertTriangle, MoreVertical, Lock } from '@lucide/vue'
import RichContent from './rich-editor/RichContent.vue'
import AnswerDisplay from './AnswerDisplay.vue'
import { isEmptyRichDoc, richDocToPlainText } from './rich-editor/richDoc'
import CompositionQuickAdd from './CompositionQuickAdd.vue'
import { useQuestionBasket } from '@/composables/useQuestionBasket'
import type { Question as DbQuestion, KnowledgePoint, OptionSpec } from '@/types'
import type { ImportDraft } from '@/lib/questionModel'
import { hasOptionPool } from '@/lib/questionModel'
import { formatDate, formatDateTime } from '@/lib/locale'
import { toast } from 'vue-sonner'

// Support both import drafts (v2, not yet persisted) and database questions
interface Props {
  item: ImportDraft | DbQuestion
  index?: number
  mode?: 'import' | 'library'
  allKnowledgePoints?: KnowledgePoint[]
  selected?: boolean
  selectable?: boolean
  hideDelete?: boolean
  hideDuplicate?: boolean
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
  hideDuplicate: false,
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

const { t } = useI18n()
const { $api } = useNuxtApp()

const isReviewing = ref(false)
const handleReview = async () => {
  if (props.mode !== 'library') return
  isReviewing.value = true
  try {
    // 只表达审核意图，是否达到发布所需审核次数由后端依据学科配置判定。
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
  const typeKeys: Record<string, string> = {
    'single_choice': 'questions.types.singleChoice',
    'multiple_choice': 'questions.types.multipleChoice',
    'true_false': 'questions.types.trueFalse',
    'fill_in_the_blank': 'questions.types.fillInTheBlank',
    'free_response': 'questions.types.freeResponse',
    'option_matching': 'questions.types.optionMatching'
  }
  const key = typeKeys[props.item.q_type]
  return key ? t(key) : props.item.q_type
})

// Kept intentionally low-saturation so type colors don't compete with the primary theme color.
const typeColor = computed(() => {
  const colors: Record<string, string> = {
    'single_choice': 'bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400',
    'multiple_choice': 'bg-violet-50 text-violet-700 dark:bg-violet-500/10 dark:text-violet-400',
    'true_false': 'bg-teal-50 text-teal-700 dark:bg-teal-500/10 dark:text-teal-400',
    'fill_in_the_blank': 'bg-orange-50 text-orange-700 dark:bg-orange-500/10 dark:text-orange-400',
    'free_response': 'bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400',
    'option_matching': 'bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-400'
  }
  return colors[props.item.q_type] || 'bg-muted text-muted-foreground'
})

const warnings = computed<string[]>(() => {
  if (props.mode !== 'import') return []
  const w = (props.item as ImportDraft).warnings
  return Array.isArray(w) ? w : []
})

const difficultyLabel = computed(() => {
  return t('questionItem.difficultyValue', { level: props.item.difficulty })
})

const copyId = async () => {
  try {
    await navigator.clipboard.writeText(String(props.item.id))
    toast.success(t('questionItem.idCopied', { id: props.item.id }))
  } catch {
    toast.error(t('questionItem.copyFailed'))
  }
}

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
  toast.success(wasInBasket ? t('basket.removed') : t('basket.added'))
}

const expanded = ref(props.defaultExpanded)

const statusLabel = computed(() => {
  const item = props.item as DbQuestion
  if (item.status === 'published') return t('questions.statuses.published')
  if (item.status === 'draft') return t('questions.statuses.draft')
  if (item.status === 'pending') {
    if (item.subject?.required_review_count && item.subject.required_review_count > 1) {
      return t('questions.statuses.pendingProgress', { count: item.review_count || 0, required: item.subject.required_review_count })
    }
    return t('questions.statuses.pending')
  }
  if (item.status === 'archived') return t('questions.statuses.archived')
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
  const item = props.item as ImportDraft
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
const importOptions = computed<OptionSpec[]>(() => (props.item as ImportDraft).options || [])

const knowledgePointIds = computed(() => {
  const item = props.item as ImportDraft
  return item.knowledge_point_ids || []
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

const sourcePreviewQuery = computed(() => {
  const task = (props.item as DbQuestion).import_task
  return task?.has_source ? { task: String(task.id), name: task.original_filename } : null
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
              <Badge
                variant="outline"
                role="button"
                tabindex="0"
                class="font-mono text-xs cursor-pointer select-none hover:bg-muted"
                :title="t('questionItem.copyIdTitle', { id: item.id })"
                @click="copyId"
                @keydown.enter="copyId"
              >#{{ item.id }}</Badge>
              <Badge v-if="(item as DbQuestion).status" :variant="statusBadgeProps.variant" :class="['text-xs', statusBadgeProps.class]">
                {{ statusLabel }}
              </Badge>
              <Badge variant="outline">{{ typeLabel }}</Badge>

              <!-- 私有题标记 -->
              <Badge v-if="(item as DbQuestion).visibility === 'private'" variant="secondary" class="flex items-center gap-1 px-1.5 bg-amber-50 text-amber-700 hover:bg-amber-100 dark:bg-amber-500/10 dark:text-amber-400">
                <Lock class="w-3 h-3" /> {{ t('questionItem.private') }}
              </Badge>

              <Badge v-if="(item as DbQuestion).stimulus_id != null" as-child variant="secondary">
                <NuxtLink :to="`/materials/${(item as DbQuestion).stimulus_id}/edit?focus=${(item as DbQuestion).id}`">
                  {{ t('questionItem.materialLink', { id: (item as DbQuestion).stimulus_id }) }}
                </NuxtLink>
              </Badge>

              <!-- Fixed 5-star scale so difficulty is comparable at a glance across items -->
              <div class="flex items-center gap-1" :title="difficultyLabel">
                <span class="text-xs text-muted-foreground">{{ t('questionItem.difficulty') }}</span>
                <Star v-for="i in 5" :key="i"
                  class="h-3 w-3"
                  :class="i <= item.difficulty ? 'fill-primary text-primary' : 'fill-none text-muted-foreground/30'" />
              </div>
            </div>
          </div>

          <!-- Actions -->
          <div class="flex gap-1">

            <Button
              variant="ghost"
              size="icon"
              class="h-8 w-8"
              :title="t('common.edit')"
              @click="emit('edit')"
            >
              <Pencil class="h-4 w-4" />
            </Button>

            <Button
              v-if="mode === 'library' && (item as DbQuestion).status === 'pending'"
              variant="ghost"
              size="icon"
              class="h-8 w-8 text-green-600 hover:text-green-700 hover:bg-green-50 dark:hover:bg-green-500/10"
              :title="t('questionItem.approve')"
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
              :title="inBasket ? t('basket.remove') : t('basket.add')"
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
              v-if="sourcePreviewQuery"
              as-child
              variant="ghost"
              size="icon"
              class="h-8 w-8 text-muted-foreground"
              :title="t('questionItem.viewSource')"
            >
              <NuxtLink :to="{ path: '/preview', query: sourcePreviewQuery }" target="_blank">
                <FileText class="h-4 w-4" />
              </NuxtLink>
            </Button>

            <!-- Lower-frequency/destructive actions grouped to reduce icon clutter -->
            <DropdownMenu v-if="mode === 'library'">
              <DropdownMenuTrigger as-child>
                <Button variant="ghost" size="icon" class="h-8 w-8" :title="t('common.moreActions')">
                  <MoreVertical class="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem
                  v-if="!hideDecompose"
                  @click="emit('decompose', item as DbQuestion)"
                >
                  <GitFork class="h-4 w-4" />
                  {{ t('questionItem.createDerived') }}
                </DropdownMenuItem>
                <DropdownMenuItem
                  v-if="(item as DbQuestion).incoming_relation_count || (item as DbQuestion).outgoing_relation_count"
                  @click="emit('view-structure', item as DbQuestion)"
                >
                  <Workflow class="h-4 w-4" />
                  {{ t('questionItem.viewDerived') }}
                </DropdownMenuItem>
                <DropdownMenuItem
                  v-if="!hideDelete"
                  variant="destructive"
                  @click="emit('delete')"
                >
                  <Trash2 class="h-4 w-4" />
                  {{ t('common.delete') }}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>

            <Button
              v-if="mode === 'import' && !hideDuplicate"
              variant="ghost"
              size="icon"
              class="h-8 w-8"
              :title="t('common.copy')"
              @click="emit('duplicate')"
            >
              <Copy class="h-4 w-4" />
            </Button>
            
            <Button
              v-if="!hideDelete && mode !== 'library'"
              variant="ghost"
              size="icon"
              class="h-8 w-8 text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-500/10"
              :title="t('common.delete')"
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
            <RichContent :content="(item as DbQuestion).content" :empty-text="t('questionItem.emptyContent')" />
          </div>
          <div v-else class="prose prose-sm max-w-none dark:prose-invert text-sm mb-2">
            <RichContent :content="(item as ImportDraft).content" :empty-text="t('questionItem.emptyContent')" />
          </div>
          
          <!-- Options for choice questions -->
          <div v-if="mode === 'library' && dbOptions.length > 0 && hasOptionPool(item.q_type)" class="mt-2 mb-3 flex flex-wrap gap-x-6 gap-y-1.5">
            <div v-for="opt in dbOptions" :key="opt.id" class="flex max-w-full gap-2 items-baseline text-xs">
              <span class="font-bold text-muted-foreground shrink-0">{{ opt.label }}.</span>
              <div class="min-w-0 text-foreground/80 [&_.prose]:my-0 [&_.prose_p]:my-0 [&_.prose]:text-xs [&_.prose]:leading-normal">
                <RichContent :content="opt.content" />
              </div>
            </div>
          </div>
          <div v-else-if="mode !== 'library' && importOptions.length > 0 && hasOptionPool(item.q_type)" class="mt-2 mb-3 flex flex-wrap gap-x-6 gap-y-1.5">
            <div v-for="opt in importOptions" :key="opt.id" class="flex max-w-full gap-2 items-baseline text-xs">
              <span class="font-bold text-muted-foreground shrink-0">{{ opt.label }}.</span>
              <div class="min-w-0 text-foreground/80 [&_.prose]:my-0 [&_.prose_p]:my-0 [&_.prose]:text-xs [&_.prose]:leading-normal">
                <RichContent :content="opt.content" />
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
                  {{ t('questionItem.knowledgePointCount', { count: knowledgePointIds.length }) }}
               </Badge>
            </template>
            <Badge v-else variant="outline" class="text-xs text-orange-600">{{ t('questionItem.noKnowledgePoint') }}</Badge>
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
            <span class="text-xs">{{ expanded ? t('questionItem.collapse') : t('questionItem.expand') }}</span>
            <ChevronDown class="h-4 w-4 transition-transform duration-200" :class="{ 'rotate-180': expanded }" />
          </Button>
        </div>
      </div>

      <!-- Expandable Details (import mode) -->
      <div v-if="mode === 'import' && expanded" class="mt-4 pt-4 border-t border-border/50 space-y-4">
        <div class="space-y-2">
          <div class="text-sm font-semibold text-foreground">{{ t('questionItem.answer') }}</div>
          <div class="text-sm bg-muted/30 p-2 rounded">
            <AnswerDisplay :answer="(item as ImportDraft).answer" :options="(item as ImportDraft).options" :empty-text="t('questionItem.notFilled')" />
          </div>
        </div>

        <div v-if="!isEmptyRichDoc((item as ImportDraft).thinking)" class="space-y-2">
          <div class="text-sm font-semibold text-foreground">{{ t('questionItem.thinking') }}</div>
          <div class="text-sm bg-muted/20 p-3 rounded [&_.prose]:my-0 [&_.prose_p]:my-0">
            <RichContent :content="(item as ImportDraft).thinking" />
          </div>
        </div>

        <div v-if="!isEmptyRichDoc((item as ImportDraft).analysis)" class="space-y-2">
          <div class="text-sm font-semibold text-foreground">{{ t('questionItem.analysis') }}</div>
          <div class="text-sm bg-muted/20 p-3 rounded [&_.prose]:my-0 [&_.prose_p]:my-0">
            <RichContent :content="(item as ImportDraft).analysis" />
          </div>
        </div>
      </div>

      <!-- Expandable Details (library mode) -->
      <div v-if="mode === 'library' && expanded" class="mt-4 pt-4 border-t border-border/50 space-y-4">
        <div class="space-y-2">
          <div class="text-sm font-semibold text-foreground">{{ t('questionItem.answer') }}</div>
          <div class="text-sm bg-muted/30 p-2 rounded">
            <AnswerDisplay :answer="(item as DbQuestion).answer" :options="(item as DbQuestion).options" />
          </div>
        </div>

        <div v-if="!isEmptyRichDoc((item as DbQuestion).thinking)" class="space-y-2">
          <div class="text-sm font-semibold text-foreground">{{ t('questionItem.thinking') }}</div>
          <div class="text-sm bg-muted/20 p-3 rounded [&_.prose]:my-0 [&_.prose_p]:my-0">
            <RichContent :content="(item as DbQuestion).thinking" />
          </div>
        </div>

        <div v-if="!isEmptyRichDoc((item as DbQuestion).analysis)" class="space-y-2">
          <div class="text-sm font-semibold text-foreground">{{ t('questionItem.analysis') }}</div>
          <div class="text-sm bg-muted/20 p-3 rounded [&_.prose]:my-0 [&_.prose_p]:my-0">
            <RichContent :content="(item as DbQuestion).analysis" />
          </div>
        </div>

        <div v-if="!isEmptyRichDoc((item as DbQuestion).summary)" class="space-y-2">
          <div class="text-sm font-semibold text-foreground">{{ t('questionItem.summary') }}</div>
          <div class="text-sm bg-muted/20 p-3 rounded [&_.prose]:my-0 [&_.prose_p]:my-0">
            <RichContent :content="(item as DbQuestion).summary" />
          </div>
        </div>

        <!-- Audit metadata: secondary info, pushed to the footer so answer/analysis surface first -->
        <div class="text-xs text-muted-foreground flex flex-col gap-1.5 pt-3 border-t border-border/50">
          <div class="flex flex-wrap gap-x-6 gap-y-1">
            <div>
              <span class="font-medium">{{ t('questionItem.createdBy') }}</span> {{ (item as DbQuestion).creator?.full_name || (item as DbQuestion).creator?.username || t('common.unknown') }}
              <span class="ml-1">{{ formatDateTime((item as DbQuestion).created_at + 'Z') }}</span>
            </div>
            <div>
              <span class="font-medium">{{ t('questionItem.updatedBy') }}</span> {{ (item as DbQuestion).updater?.full_name || (item as DbQuestion).updater?.username || t('common.unknown') }}
              <span class="ml-1">{{ formatDateTime((item as DbQuestion).updated_at + 'Z') }}</span>
            </div>
          </div>
          <div class="flex flex-col gap-1">
            <div class="flex items-center gap-2">
              <span class="font-medium">{{ t('questionItem.reviewCount') }}</span> {{ (item as DbQuestion).review_count }}
            </div>
            <div v-if="(item as DbQuestion).review_logs?.length" class="flex gap-1 flex-wrap mt-1">
               <span v-for="log in (item as DbQuestion).review_logs" :key="log.id" class="bg-muted px-2 py-0.5 rounded text-[10px] flex items-center gap-1">
                  <History class="w-3 h-3" />
                  {{ log.user?.full_name || log.user?.username }} ({{ formatDate(log.created_at + 'Z') }})
               </span>
            </div>
          </div>
          <div v-if="(item as DbQuestion).source">
            <span class="font-medium">{{ t('questionItem.source') }}</span> {{ (item as DbQuestion).source }}
          </div>
        </div>
      </div>
    </div>
  </Card>
</template>
