<script setup lang="ts">
import { ArchiveRestore, ChevronDown, ChevronRight, FilePenLine, FilePlus2, Layers3, Loader2, Lock, Trash2 } from '@lucide/vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import RichContent from '@/components/rich-editor/RichContent.vue'
import { questionTypeLabel } from '@/lib/answerFormat'
import { getApiErrorDetail } from '@/lib/apiErrors'
import type { QuestionSummary, StimulusListItem } from '@/types'

const props = defineProps<{
  stimulus: StimulusListItem
  canEdit: boolean
}>()

defineEmits<{
  delete: [stimulus: StimulusListItem]
  restore: [stimulus: StimulusListItem]
  addComposition: [stimulus: StimulusListItem]
}>()

const isDeleted = computed(() => props.stimulus.deleted_at !== null)
const { getStimulus } = useStimuli()

const expanded = ref(false)
const questions = ref<QuestionSummary[] | null>(null)
const loadingQuestions = ref(false)
const loadError = ref('')

// 展开时才加载小题;列表刷新(revision 变化)后重新取。
watch(() => props.stimulus.revision, () => { questions.value = null })
const toggleQuestions = async () => {
  expanded.value = !expanded.value
  if (!expanded.value || questions.value || loadingQuestions.value) return
  loadingQuestions.value = true
  loadError.value = ''
  try {
    questions.value = (await getStimulus(props.stimulus.subject_id, props.stimulus.id)).questions
  } catch (error) {
    loadError.value = getApiErrorDetail(error, '小题加载失败')
  } finally {
    loadingQuestions.value = false
  }
}

const statusLabel: Record<string, string> = {
  draft: '草稿',
  pending: '待审核',
  published: '已发布',
  archived: '已归档',
}
</script>

<template>
  <article class="border-b px-1 py-4 last:border-b-0">
    <div class="flex items-start gap-4">
      <div class="min-w-0 flex-1 space-y-3">
        <div class="flex flex-wrap items-center gap-2">
          <span class="font-mono text-xs text-muted-foreground">#{{ stimulus.id }}</span>
          <Badge variant="secondary">{{ statusLabel[stimulus.status] || stimulus.status }}</Badge>
          <Badge v-if="stimulus.visibility === 'private'" variant="outline" class="gap-1">
            <Lock class="size-3" /> 私有
          </Badge>
          <span v-if="stimulus.source" class="truncate text-xs text-muted-foreground">{{ stimulus.source }}</span>
        </div>
        <RichContent :content="stimulus.content" empty-text="（空材料）" class="line-clamp-4 text-sm" />
        <Badge v-if="stimulus.question_count === 0" variant="outline" class="border-amber-500/50 text-amber-700 dark:text-amber-400">待出题</Badge>
        <template v-else>
          <button
            type="button"
            class="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
            :aria-expanded="expanded"
            @click="toggleQuestions"
          >
            <component :is="expanded ? ChevronDown : ChevronRight" class="size-3.5" />
            <Layers3 class="size-3.5" />
            {{ stimulus.question_count }} 道小题<template v-if="stimulus.composition_count"> · 被 {{ stimulus.composition_count }} 份稿件使用</template>
          </button>
          <div v-if="expanded" class="ml-5 border-l pl-3">
            <div v-if="loadingQuestions" class="py-2"><Loader2 class="size-4 animate-spin text-muted-foreground" /></div>
            <p v-else-if="loadError" class="py-2 text-xs text-destructive">{{ loadError }}</p>
            <ol v-else class="space-y-2">
              <li v-for="(question, index) in questions" :key="question.id" class="flex items-start gap-2 text-sm">
                <span class="shrink-0 text-xs text-muted-foreground">{{ index + 1 }}.</span>
                <RichContent :content="question.content" empty-text="（空题干）" class="line-clamp-2 min-w-0 flex-1" />
                <span class="shrink-0 text-xs text-muted-foreground">{{ questionTypeLabel(question.q_type) }}</span>
              </li>
            </ol>
          </div>
        </template>
      </div>
      <div class="flex shrink-0 items-center gap-1">
        <Button
          v-if="!isDeleted && stimulus.question_count > 0"
          variant="ghost"
          size="icon"
          title="整道材料题加入稿件"
          aria-label="整道材料题加入稿件"
          @click="$emit('addComposition', stimulus)"
        >
          <FilePlus2 class="size-4" />
        </Button>
        <template v-if="canEdit">
          <Button v-if="isDeleted" variant="ghost" size="icon" title="恢复材料题" aria-label="恢复材料题" @click="$emit('restore', stimulus)">
            <ArchiveRestore class="size-4" />
          </Button>
          <template v-else>
            <Button as-child variant="ghost" size="icon" title="编辑材料题" aria-label="编辑材料题">
              <NuxtLink :to="`/materials/${stimulus.id}/edit`"><FilePenLine class="size-4" /></NuxtLink>
            </Button>
            <Button variant="ghost" size="icon" class="text-destructive" title="删除材料题" aria-label="删除材料题" @click="$emit('delete', stimulus)">
              <Trash2 class="size-4" />
            </Button>
          </template>
        </template>
      </div>
    </div>
  </article>
</template>