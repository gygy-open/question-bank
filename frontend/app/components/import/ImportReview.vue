<script setup lang="ts">
import { getApiErrorCodeMessage, getApiErrorDetail } from '@/lib/apiErrors'
import { ref, computed, watch, onMounted } from 'vue'
import { Loader2, FileText, AlertCircle, Save, ChevronDown, Trash2 } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import QuestionListItem from '@/components/QuestionListItem.vue'
import QuestionGroupReview from '@/components/import/QuestionGroupReview.vue'
import ImportDuplicateNotice from '@/components/dedup/ImportDuplicateNotice.vue'
import QuestionEditDialog from '@/components/QuestionEditDialog.vue'
import type { DuplicateCandidate, IntraBatchDuplicate } from '@/lib/questionDedup'
import { useDebounceFn } from '@vueuse/core'
import { toast } from 'vue-sonner'
import type { CompositionFolder, CompositionScope, KnowledgePoint, Subject } from '@/types'
import { buildFolderTree } from '@/lib/compositions'
import { hasPaperStructure, insertQuestionRefAfter, type PaperExtraction } from '@/lib/paperOutline'
import {
  buildImportReviewEntries,
  buildImportStructurePayload,
  validateImportStructure,
  type ImportQuestionGroup,
  type ImportStimulus,
} from '@/lib/importReview'
import {
  type ImportDraft,
  type ExtractedQuestionItem,
  extractedItemToDraft,
  buildQuestionPayload,
  generateTempId,
} from '@/lib/questionModel'
import type { ImportTaskItem } from '@/composables/useImportQueue'

const props = defineProps<{ task: ImportTaskItem }>()
const emit = defineEmits<{ committed: []; discarded: [] }>()

const { t } = useI18n()
const { $api } = useNuxtApp()
useAiScene().useSceneWhileMounted('import_review')

interface DuplicateOf {
  import_task_id: number
  original_filename: string | null
  imported_at: string | null
  composition_id: number | null
  composition_scope: CompositionScope | null
}

const step = ref<'loading' | 'review' | 'unavailable'>('loading')
const isImporting = ref(false)
const importList = ref<ImportDraft[]>([])
const stimuli = ref<ImportStimulus[]>([])
const questionGroups = ref<ImportQuestionGroup[]>([])
const paper = ref<PaperExtraction | null>(null)
const warnings = ref<string[]>([])
const contentSha256 = ref<string | null>(null)
const duplicateOf = ref<DuplicateOf | null>(null)
const editingItemId = ref<string | null>(null)

// 默认关闭：只有用户主动勾选才会建稿。
const saveAsComposition = ref(false)
const compositionScope = ref<CompositionScope>('personal')
const compositionTitle = ref('')
const compositionFolderId = ref<number | null>(null)
const renumber = ref(true)
const folders = ref<CompositionFolder[]>([])
const idempotencyKey = ref<string | null>(null)
const partialFailureDetail = ref<string | null>(null)

const reviewSettings = ref({
  status: 'pending' as 'draft' | 'pending' | 'published',
  source: '' as string,
})
const subjectId = computed(() => props.task.subject_id ?? undefined)

const { data: subjects } = useAPI<Subject[]>('/subjects')
const { data: knowledgePoints } = useAPI<KnowledgePoint[]>('/knowledge-points', { query: { limit: -1 } })

const folderOptions = computed(() => {
  const tree = buildFolderTree(folders.value)
  const flat: { id: number; label: string }[] = []
  const walk = (nodes: typeof tree, depth: number) => {
    for (const node of nodes) {
      flat.push({ id: node.id, label: `${'　'.repeat(depth)}${node.name}` })
      walk(node.children, depth + 1)
    }
  }
  walk(tree, 0)
  return flat
})

const hasStructure = computed(() => hasPaperStructure(paper.value))
const warningCount = computed(() => importList.value.filter((i) => i.warnings?.length).length)
const selectedCount = computed(() => importList.value.filter((item) => item.selected).length)
const onlyWarnings = ref(false)
const structureErrors = computed(() => validateImportStructure(importList.value, stimuli.value, questionGroups.value, paper.value))
const reviewEntries = computed(() => buildImportReviewEntries(importList.value, stimuli.value, questionGroups.value, paper.value))
const visibleReviewEntries = computed(() => {
  if (!onlyWarnings.value) return reviewEntries.value
  return reviewEntries.value.filter((entry) => entry.kind === 'question'
    ? entry.question.warnings?.length
    : entry.members.some(({ question }) => question.warnings?.length))
})

const loadResult = async () => {
  step.value = 'loading'
  try {
    const data = await $api<any>(`/imports/${props.task.id}/result`)
    importList.value = ((data.questions ?? []) as ExtractedQuestionItem[])
      .map((it) => extractedItemToDraft(it, { subjectId: subjectId.value }))
    stimuli.value = data.stimuli ?? []
    questionGroups.value = data.question_groups ?? []
    const groupedQuestionIds = new Set(questionGroups.value.flatMap((group) => group.question_temp_ids))
    for (const draft of importList.value) {
      if (draft.temp_id && groupedQuestionIds.has(draft.temp_id)) draft.selected = true
    }
    paper.value = data.paper ?? null
    warnings.value = data.warnings ?? []
    contentSha256.value = data.content_sha256 ?? null
    duplicateOf.value = data.duplicate_of ?? null
    compositionTitle.value = (paper.value?.suggested_title || props.task.original_filename || '').replace(/\.[^.]+$/, '')
    duplicates.value = {}
    batchDuplicates.value = {}
    duplicatesApplied.value = false
    step.value = 'review'
  } catch {
    step.value = 'unavailable'
  }
}
onMounted(loadResult)

const loadFolders = async () => {
  if (!subjectId.value) return
  try {
    folders.value = await $api<CompositionFolder[]>(`/subjects/${subjectId.value}/folders`, {
      query: { scope: compositionScope.value },
    })
  } catch {
    folders.value = []
  }
}

// 切换空间会换一棵目录树，已选目录必须重置。
watch(compositionScope, () => {
  compositionFolderId.value = null
  loadFolders()
})
watch(saveAsComposition, (on) => {
  if (on) loadFolders()
})

// 逐条应用审核设置；缺答案的题降级为草稿（与后端 adapter 对齐）。
const toPayloadQuestion = (item: ImportDraft) => {
  const d: ImportDraft = JSON.parse(JSON.stringify(item))
  d.subject_id = d.subject_id || subjectId.value
  d.source = reviewSettings.value.source || ''
  d.status = d.answer ? reviewSettings.value.status : 'draft'
  return {
    ...buildQuestionPayload(d),
    ai_suggested_tags: d.ai_suggested_tags,
    temp_id: d.temp_id,
    parent_temp_id: d.parent_temp_id,
  }
}

// --- 查重 ---
// 进入审核后对全部题目预检(与题库比对 + 批内互查)。命中「重复」的独立题在每次加载后
// 默认取消勾选一次;之后以用户勾选为准 —— 勾选即视为确认录入。材料题的小题不能单独取消,只做标记。
const duplicates = ref<Record<string, DuplicateCandidate[]>>({})
const batchDuplicates = ref<Record<string, IntraBatchDuplicate[]>>({})
const duplicatesApplied = ref(false)

const groupedTempIds = computed(() => new Set(questionGroups.value.flatMap((group) => group.question_temp_ids)))
const questionNumberOf = (ref: string) => {
  const index = importList.value.findIndex((item) => item.temp_id === ref)
  return index >= 0 ? index + 1 : undefined
}
const isFlagged = (item: ImportDraft) =>
  !!item.temp_id && !!(duplicates.value[item.temp_id]?.length || batchDuplicates.value[item.temp_id]?.length)
const duplicateSummary = computed(() => {
  let existing = 0
  let similar = 0
  let batch = 0
  for (const item of importList.value) {
    if (!item.temp_id) continue
    const found = duplicates.value[item.temp_id] ?? []
    if (found.some((c) => c.level === 'duplicate')) existing++
    else if (found.length) similar++
    if (batchDuplicates.value[item.temp_id]?.length) batch++
  }
  return { existing, similar, batch, flagged: existing + similar + batch }
})

const dedupSignature = computed(() => step.value === 'review' && subjectId.value
  ? JSON.stringify([
      subjectId.value,
      importList.value.map((item) => [item.temp_id, item.q_type, item.content, item.options]),
      stimuli.value,
      questionGroups.value,
    ])
  : null)

const refreshDuplicates = useDebounceFn(async (signature: string | null) => {
  if (!signature || !subjectId.value) {
    duplicates.value = {}
    batchDuplicates.value = {}
    return
  }
  try {
    const structurePayload = buildImportStructurePayload(
      importList.value.map(toPayloadQuestion),
      importList.value,
      stimuli.value,
      questionGroups.value,
      paper.value,
    )
    const res = await $api<{
      duplicates: Record<string, DuplicateCandidate[]>
      intra_batch_duplicates: Record<string, IntraBatchDuplicate[]>
    }>(`/subjects/${subjectId.value}/paper-imports/preview`, {
      method: 'POST',
      body: { scope: compositionScope.value, ...structurePayload },
    })
    if (signature !== dedupSignature.value) return
    duplicates.value = res.duplicates ?? {}
    batchDuplicates.value = res.intra_batch_duplicates ?? {}
    if (!duplicatesApplied.value) {
      duplicatesApplied.value = true
      for (const item of importList.value) {
        if (!item.temp_id || groupedTempIds.value.has(item.temp_id)) continue
        const exact = duplicates.value[item.temp_id]?.some((c) => c.level === 'duplicate')
          || batchDuplicates.value[item.temp_id]?.some((b) => b.level === 'duplicate')
        if (exact) item.selected = false
      }
    }
  } catch {
    // 预检失败不影响导入,提交时后端仍会复核
  }
}, 600)

watch(dedupSignature, (signature) => { refreshDuplicates(signature) })

const handleImport = async (proceedWithPartial = false) => {
  if (!subjectId.value) {
    toast.error(t('imports.review.noSubject'))
    return
  }
  if (structureErrors.value.length > 0) {
    toast.error(t('importSmart.review.structureInvalidToast'))
    return
  }
  const selectedItems = importList.value.filter(item => item.selected)
  if (selectedItems.length === 0) {
    toast.error(t('importSmart.review.selectAtLeastOne'))
    return
  }
  if (saveAsComposition.value && !compositionTitle.value.trim()) {
    toast.error(t('importSmart.review.compositionTitleRequired'))
    return
  }

  isImporting.value = true
  try {
    const payloadQuestions = selectedItems.map(toPayloadQuestion)
    // 幂等键绑定本次提交：网络重试不会重复建题建稿。
    idempotencyKey.value ||= generateTempId()

    const structurePayload = buildImportStructurePayload(
      payloadQuestions,
      selectedItems,
      stimuli.value,
      questionGroups.value,
      paper.value,
    )
    const preview = await $api<{
      importable_count: number
      skipped: { temp_id: string | null; message: string }[]
      blocking_reason: string | null
      blocking_code?: string | null
      blocking_params?: Record<string, unknown> | null
    }>(`/subjects/${subjectId.value}/paper-imports/preview`, {
      method: 'POST',
      body: { scope: compositionScope.value, ...structurePayload },
    })
    if (preview.blocking_reason) {
      toast.error(t('importSmart.review.previewFailed'), {
        description: getApiErrorCodeMessage({ data: { code: preview.blocking_code, params: preview.blocking_params } }) || preview.blocking_reason,
      })
      return
    }
    if (preview.skipped.length > 0 && !proceedWithPartial) {
      partialFailureDetail.value = t('importSmart.review.partialSkipped', {
        count: preview.skipped.length,
        messages: preview.skipped.map((item) => item.message).join(t('importSmart.review.messageSeparator')),
      })
      return
    }

    const res = await $api<any>(`/subjects/${subjectId.value}/paper-imports`, {
      method: 'POST',
      body: {
        scope: compositionScope.value,
        ...structurePayload,
        save_as_composition: saveAsComposition.value,
        title: compositionTitle.value.trim() || null,
        folder_id: compositionFolderId.value,
        renumber: renumber.value,
        proceed_with_partial: proceedWithPartial,
        status: reviewSettings.value.status,
        filename: props.task.original_filename,
        content_sha256: contentSha256.value,
        idempotency_key: idempotencyKey.value,
        import_task_id: props.task.id,
        // 用户仍勾选的疑似重复题视为已确认
        allow_duplicate_temp_ids: selectedItems.filter(isFlagged).map((item) => item.temp_id),
      },
    })

    const skipped = res.skipped?.length ?? 0
    if (skipped > 0) {
      toast.warning(t('importSmart.review.importedWithSkipped', { skipped, created: res.created_count }))
    } else {
      toast.success(t('importSmart.review.imported', { count: res.created_count }))
    }
    emit('committed')
  } catch (e: any) {
    // 422 且尚未决定如何处理部分失败时，交由用户选择继续或取消。
    if (e?.data?.code === 'paper_import.partial_skipped' && !proceedWithPartial) {
      partialFailureDetail.value = getApiErrorDetail(e, e.message)
      return
    }
    toast.error(t('importSmart.review.importFailed'), { description: getApiErrorDetail(e, e.message) })
  } finally {
    isImporting.value = false
  }
}

const confirmPartialImport = async () => {
  partialFailureDetail.value = null
  await handleImport(true)
}

const isDiscarding = ref(false)
const discard = async () => {
  if (!confirm(t('imports.detail.discardConfirm'))) return
  isDiscarding.value = true
  try {
    await $api<unknown>(`/imports/${props.task.id}/cancel`, { method: 'POST' })
    toast.success(t('imports.detail.discarded'))
    emit('discarded')
  } catch (e: any) {
    toast.error(getApiErrorDetail(e, e.message))
  } finally {
    isDiscarding.value = false
  }
}

const removeItem = (index: number) => {
  const item = importList.value[index]
  if (paper.value?.outline && item?.temp_id) {
    paper.value = {
      ...paper.value,
      outline: paper.value.outline.filter(
        (outlineItem) => outlineItem.kind !== 'question_ref' || outlineItem.temp_id !== item.temp_id,
      ),
    }
  }
  importList.value.splice(index, 1)
}

const duplicateItem = (index: number) => {
  const item = importList.value[index]
  if (!item) return
  const newItem: ImportDraft = JSON.parse(JSON.stringify(item))
  newItem.uid = `imp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  newItem.temp_id = generateTempId()
  importList.value.splice(index + 1, 0, newItem)
  // 版面上也要多出一道题，否则副本不会出现在稿件里。
  if (paper.value?.outline && item.temp_id && newItem.temp_id) {
    paper.value = {
      ...paper.value,
      outline: insertQuestionRefAfter(paper.value.outline, item.temp_id, newItem.temp_id),
    }
  }
}

const editItem = (uid: string) => {
  editingItemId.value = uid
}

const handleEditSuccess = (updatedQuestion: ImportDraft) => {
  if (editingItemId.value) {
    const index = importList.value.findIndex(i => i.uid === editingItemId.value)
    if (index !== -1) importList.value[index] = updatedQuestion
  }
  editingItemId.value = null
}

const getEditingItem = () => importList.value.find(item => item.uid === editingItemId.value)

const duplicateCompositionLink = computed(() => {
  const dup = duplicateOf.value
  if (!dup?.composition_id) return null
  return `/compositions/${dup.composition_scope ?? 'shared'}/${dup.composition_id}`
})
</script>

<template>
  <div v-if="step === 'loading'" class="space-y-3">
    <Skeleton class="h-24 w-full" />
    <Skeleton class="h-24 w-full" />
    <Skeleton class="h-24 w-full" />
  </div>

  <Alert v-else-if="step === 'unavailable'" variant="destructive">
    <AlertCircle class="h-4 w-4" />
    <AlertDescription>{{ t('apiErrors.import_task.result_unavailable') }}</AlertDescription>
  </Alert>

  <div v-else-if="step === 'review'" class="space-y-4">
    <!-- 文件级重复提示：只提示，不阻塞 -->
    <Alert v-if="duplicateOf">
      <AlertCircle class="h-4 w-4" />
      <AlertDescription>
        {{ t('importSmart.review.duplicate', { filename: duplicateOf.original_filename ?? '' }) }}
        <NuxtLink v-if="duplicateCompositionLink" :to="duplicateCompositionLink" class="underline font-medium ml-1">
          {{ t('importSmart.review.viewLastComposition') }}
        </NuxtLink>
      </AlertDescription>
    </Alert>

    <Alert v-if="warnings.length">
      <AlertCircle class="h-4 w-4" />
      <AlertDescription>
        <ul class="list-disc space-y-1 pl-4">
          <li v-for="(w, i) in warnings" :key="i">{{ w }}</li>
        </ul>
      </AlertDescription>
    </Alert>

    <Alert v-if="structureErrors.length" variant="destructive">
      <AlertCircle class="h-4 w-4" />
      <AlertDescription>
        <p class="font-medium">{{ t('importSmart.review.structureInvalid') }}</p>
        <ul class="mt-2 list-disc space-y-1 pl-5">
          <li v-for="message in structureErrors" :key="message">{{ message }}</li>
        </ul>
      </AlertDescription>
    </Alert>
    <div v-if="importList.length === 0" class="text-center py-8 text-muted-foreground">
      {{ t('imports.review.empty') }}
    </div>
    <Alert v-if="duplicateSummary.flagged" class="border-amber-500/50 bg-amber-500/5">
      <AlertCircle class="h-4 w-4 text-amber-600" />
      <AlertDescription>
        {{ t('questionDedup.import.summary', { total: importList.length, existing: duplicateSummary.existing, similar: duplicateSummary.similar, batch: duplicateSummary.batch }) }}
      </AlertDescription>
    </Alert>

    <template v-for="entry in visibleReviewEntries" :key="entry.kind === 'question' ? entry.question.uid : entry.group.temp_id">
      <ImportDuplicateNotice
        v-if="entry.kind === 'question' && entry.question.temp_id"
        :candidates="duplicates[entry.question.temp_id]"
        :batch="batchDuplicates[entry.question.temp_id]"
        :number-of="questionNumberOf"
      />
      <QuestionListItem
        v-if="entry.kind === 'question'"
        :item="entry.question"
        :index="entry.index"
        :all-knowledge-points="knowledgePoints"
        :selected="entry.question.selected"
        selectable
        @select="entry.question.selected = $event"
        @edit="editItem(entry.question.uid)"
        @delete="removeItem(entry.index)"
        @duplicate="duplicateItem(entry.index)"
      />
      <QuestionGroupReview
        v-else
        :entry="entry"
        :duplicates="duplicates"
        :batch-duplicates="batchDuplicates"
        :number-of="questionNumberOf"
        :all-knowledge-points="knowledgePoints"
        @edit="editItem"
      />
    </template>

    <QuestionEditDialog
      :open="!!editingItemId"
      :question="getEditingItem()"
      :knowledge-points="knowledgePoints"
      :subjects="subjects"
      :auto-fill-subject-id="subjectId"
      mode="import"
      @update:open="(v) => !v && (editingItemId = null)"
      @save="handleEditSuccess"
    />

    <div class="sticky bottom-3 z-20 -mx-1 overflow-hidden rounded-lg border bg-background/95 shadow-[0_-8px_28px_rgba(0,0,0,0.10)] backdrop-blur supports-[backdrop-filter]:bg-background/90">
      <div v-if="saveAsComposition" class="border-b bg-muted/20 px-4 py-3">
        <div class="mb-3 flex items-center justify-between">
          <div class="flex items-center gap-2">
            <FileText class="h-4 w-4 text-primary" />
            <span class="text-sm font-medium">{{ t('importSmart.composition.settings') }}</span>
            <span class="hidden text-xs text-muted-foreground sm:inline">{{ t('importSmart.composition.hint') }}</span>
          </div>
          <Button variant="ghost" size="icon" class="h-7 w-7" :title="t('importSmart.composition.collapse')" @click="saveAsComposition = false">
            <ChevronDown class="h-4 w-4" />
            <span class="sr-only">{{ t('importSmart.composition.collapse') }}</span>
          </Button>
        </div>
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-12">
          <div class="space-y-1.5 xl:col-span-4">
            <Label class="text-xs text-muted-foreground">{{ t('importSmart.composition.title') }}</Label>
            <Input v-model="compositionTitle" :placeholder="t('importSmart.composition.titlePlaceholder')" class="h-9 bg-background" />
          </div>
          <div class="space-y-1.5 xl:col-span-3">
            <Label class="text-xs text-muted-foreground">{{ t('importSmart.composition.scope') }}</Label>
            <Select v-model="compositionScope">
              <SelectTrigger class="h-9 bg-background"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="personal">{{ t('importSmart.composition.scopePersonal') }}</SelectItem>
                <SelectItem value="shared">{{ t('importSmart.composition.scopeShared') }}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div class="space-y-1.5 xl:col-span-2">
            <Label class="text-xs text-muted-foreground">{{ t('importSmart.composition.folder') }}</Label>
            <Select
              :model-value="compositionFolderId === null ? 'root' : String(compositionFolderId)"
              @update:model-value="(v) => compositionFolderId = v === 'root' ? null : Number(v)"
            >
              <SelectTrigger class="h-9 bg-background"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="root">{{ t('importSmart.composition.rootFolder') }}</SelectItem>
                <SelectItem v-for="f in folderOptions" :key="f.id" :value="String(f.id)">{{ f.label }}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div class="space-y-1.5 xl:col-span-3">
            <Label class="text-xs text-muted-foreground">{{ t('importSmart.composition.numbering') }}</Label>
            <Select :model-value="renumber ? 'renumber' : 'keep'" @update:model-value="(v) => renumber = v === 'renumber'">
              <SelectTrigger class="h-9 bg-background"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="renumber">{{ t('importSmart.composition.renumber') }}</SelectItem>
                <SelectItem value="keep">{{ t('importSmart.composition.keepNumber') }}</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <p v-if="!hasStructure" class="mt-2 text-xs text-muted-foreground">
          {{ t('importSmart.composition.noStructure') }}
        </p>
      </div>

      <div class="flex min-h-16 flex-col gap-3 px-4 py-3 xl:flex-row xl:items-center">
        <div class="flex flex-wrap items-center gap-2 rounded-md bg-muted/40 px-2.5 py-2">
          <label class="flex shrink-0 cursor-pointer select-none items-center gap-2 text-sm font-medium">
            <Checkbox :model-value="saveAsComposition" @update:model-value="(v) => saveAsComposition = v as boolean" />
            {{ t('importSmart.composition.saveAs') }}
          </label>
          <Separator orientation="vertical" class="hidden h-5 sm:block" />
          <div class="flex items-center gap-1.5">
            <Label class="shrink-0 text-xs text-muted-foreground">{{ t('importSmart.review.status') }}</Label>
            <Select v-model="reviewSettings.status">
              <SelectTrigger class="h-8 w-[124px] bg-background text-xs"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="draft">{{ t('questions.statuses.draft') }}</SelectItem>
                <SelectItem value="pending">{{ t('questions.statuses.pending') }}</SelectItem>
                <SelectItem value="published">{{ t('questions.statuses.published') }}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div class="flex min-w-[180px] flex-1 items-center gap-1.5 sm:max-w-[260px]">
            <Label class="shrink-0 text-xs text-muted-foreground">{{ t('importSmart.review.source') }}</Label>
            <Input v-model="reviewSettings.source" :placeholder="t('importSmart.review.sourcePlaceholder')" class="h-8 bg-background text-xs" />
          </div>
        </div>
        <div class="flex flex-1 flex-wrap items-center justify-between gap-3 xl:justify-end">
          <div class="flex items-center gap-2">
            <button
              v-if="warningCount > 0"
              type="button"
              :aria-pressed="onlyWarnings"
              :title="t('importSmart.review.onlyWarnings')"
              @click="onlyWarnings = !onlyWarnings"
            >
              <Badge variant="outline" :class="onlyWarnings ? 'border-amber-500 bg-amber-500/10 text-amber-700 dark:text-amber-400' : 'text-amber-600 dark:text-amber-400'">
                <AlertCircle class="mr-1 h-3.5 w-3.5" />{{ t('importSmart.review.warningCount', { count: warningCount }) }}
              </Badge>
            </button>
            <i18n-t scope="global" keypath="importSmart.review.selected" tag="span" class="whitespace-nowrap text-sm text-muted-foreground">
              <template #selected><strong class="font-medium text-foreground">{{ selectedCount }}</strong></template>
              <template #total>{{ importList.length }}</template>
            </i18n-t>
          </div>
          <div class="flex items-center gap-2">
            <Button variant="ghost" :disabled="isImporting || isDiscarding" @click="discard">
              <Trash2 class="mr-2 h-4 w-4" />{{ t('imports.detail.discard') }}
            </Button>
            <Button class="min-w-[148px]" :disabled="isImporting || selectedCount === 0 || structureErrors.length > 0" @click="handleImport()">
              <Loader2 v-if="isImporting" class="mr-2 h-4 w-4 animate-spin" />
              <Save v-else class="mr-2 h-4 w-4" />
              {{ t('importSmart.review.confirmImport', { count: selectedCount }) }}
            </Button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- 部分失败：由用户决定继续还是取消 -->
  <Dialog :open="!!partialFailureDetail" @update:open="(v) => !v && (partialFailureDetail = null)">
    <DialogContent>
      <DialogHeader>
        <DialogTitle>{{ t('importSmart.partial.title') }}</DialogTitle>
        <DialogDescription>{{ partialFailureDetail }}</DialogDescription>
      </DialogHeader>
      <p class="text-sm text-muted-foreground">{{ t('importSmart.partial.description') }}</p>
      <DialogFooter>
        <Button variant="outline" @click="partialFailureDetail = null">{{ t('importSmart.partial.back') }}</Button>
        <Button :disabled="isImporting" @click="confirmPartialImport">
          <Loader2 v-if="isImporting" class="mr-2 h-4 w-4 animate-spin" />
          {{ t('importSmart.partial.confirm') }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
