<script setup lang="ts">
import AiPanelToggle from '~/components/chat/AiPanelToggle.vue'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import draggable from 'vuedraggable'
import { AlertTriangle, ArrowDown, ArrowLeft, ArrowUp, ChevronDown, ChevronUp, Ellipsis, FilePlus2, GripVertical, ListPlus, Loader2, Pencil, Plus, Save, Trash2, Unlink } from '@lucide/vue'
import { toast } from 'vue-sonner'
import StimulusQuestionPickerDialog from '@/components/stimuli/StimulusQuestionPickerDialog.vue'
import QuestionDraftEditor from '@/components/QuestionDraftEditor.vue'
import CompositionTargetPicker from '@/components/CompositionTargetPicker.vue'
import RichContent from '@/components/rich-editor/RichContent.vue'
import RichEditor from '@/components/rich-editor/RichEditor.vue'
import { isEmptyRichDoc } from '@/components/rich-editor/richDoc'
import { provideMediaSubject } from '@/composables/useMedia'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { questionTypeDisplayLabel } from '@/lib/answerFormat'
import { getApiErrorDetail, isRevisionConflict } from '@/lib/apiErrors'
import {
  type BundleMeta,
  type MemberEntry,
  addExisting,
  buildBundleQuestions,
  bundleSnapshot,
  effectiveMeta,
  entryFromQuestion,
  hasEditorSubjectMismatch,
  isBodyDirty,
  moveMember,
  newEntry,
  publicMembersUnderPrivate,
  validateMembers,
} from '@/lib/stimulusEditor'
import type { Question, QuestionStatus, QuestionSummary, RichDoc, StimulusDetail } from '@/types'

const props = defineProps<{ stimulusId?: number }>()
const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const { $api } = useNuxtApp()
const { currentSubjectId, setSubject } = useSubjectContext()
const { can } = usePermissions()
const { getStimulus, createStimulusBundle, updateStimulusBundle } = useStimuli()
const editorSubjectId = ref<number | null>(null)
provideMediaSubject(() => editorSubjectId.value)
const canEdit = computed(() => can(Capability.EDIT_QUESTION, editorSubjectId.value))
const isEdit = computed(() => props.stimulusId != null)
const subjectMismatch = computed(() => hasEditorSubjectMismatch(editorSubjectId.value, currentSubjectId.value))

const content = ref<RichDoc>(null)
const status = ref<QuestionStatus>('draft')
const visibility = ref<'public' | 'private'>('public')
const source = ref('')
const revision = ref<number | null>(null)
const entries = ref<MemberEntry[]>([])
const expanded = ref(new Set<string>())
const saved = ref({
  status: 'draft' as QuestionStatus,
  visibility: 'public' as 'public' | 'private',
  snapshot: '',
  questionIds: [] as number[],
})
const loading = ref(false)
const saving = ref(false)
const conflict = ref(false)
const errorMessage = ref('')
const pickerOpen = ref(false)
const compositionPickerOpen = ref(false)

const snapshot = computed(() => bundleSnapshot(
  { content: content.value, status: status.value, visibility: visibility.value, source: source.value },
  entries.value,
))
const dirty = computed(() => snapshot.value !== saved.value.snapshot)
saved.value.snapshot = snapshot.value
const meta = computed<BundleMeta>(() => ({
  status: status.value,
  visibility: visibility.value,
  syncMembers: status.value !== saved.value.status || visibility.value !== saved.value.visibility,
}))
const selectedIds = computed(() => entries.value.flatMap(entry => (entry.id == null ? [] : [entry.id])))
const incompatible = computed(() => publicMembersUnderPrivate(entries.value, meta.value))
const incompatibleMessage = computed(() => incompatible.value.length
  ? t('stimuli.form.incompatibleMessage', { items: incompatible.value.join(t('stimuli.form.listSeparator')) })
  : '')
const settingsOpen = ref(false)
// 冲突提示要求改可见性时，把设置区展开到用户眼前。
watch(incompatible, (items) => { if (items.length) settingsOpen.value = true })
const STATUS_KEYS: Record<QuestionStatus, string> = {
  draft: 'questions.statuses.draft',
  pending: 'questions.statuses.pending',
  published: 'questions.statuses.published',
  archived: 'questions.statuses.archived',
}
const visibilityLabel = (value: 'public' | 'private') => t(value === 'private' ? 'materials.filters.private' : 'materials.filters.public')
const settingsSummary = computed(() =>
  [t(STATUS_KEYS[status.value]), visibilityLabel(visibility.value), source.value.trim()].filter(Boolean).join(' · '))

const resetBaseline = (questionIds: number[]) => {
  saved.value = { status: status.value, visibility: visibility.value, snapshot: snapshot.value, questionIds }
}

const compositionCount = ref(0)
const savedContent = ref('')
// 与后端过期判断一致:材料或已有小题内容变化、小题移出;新增小题与状态变化不算。
const staleForCompositions = computed(() =>
  JSON.stringify(content.value) !== savedContent.value
  || entries.value.some(entry => entry.id != null && isBodyDirty(entry))
  || saved.value.questionIds.some(id => !selectedIds.value.includes(id)))
const impactHint = computed(() => {
  if (!isEdit.value || !dirty.value) return ''
  const parts: string[] = []
  if (meta.value.syncMembers && saved.value.questionIds.length) parts.push(t('stimuli.form.impactSyncMembers', { count: saved.value.questionIds.length }))
  if (compositionCount.value && staleForCompositions.value) parts.push(t('stimuli.form.impactCompositions', { count: compositionCount.value }))
  return parts.length ? t('stimuli.form.impactHint', { parts: parts.join(t('stimuli.form.clauseSeparator')) }) : ''
})

const applyStimulus = (stimulus: StimulusDetail) => {
  content.value = structuredClone(stimulus.content)
  status.value = stimulus.status
  visibility.value = stimulus.visibility
  source.value = stimulus.source ?? ''
  revision.value = stimulus.revision
  compositionCount.value = stimulus.composition_count ?? 0
  savedContent.value = JSON.stringify(stimulus.content)
  entries.value = stimulus.questions.map(entryFromQuestion)
  expanded.value = new Set()
  resetBaseline(stimulus.questions.map(question => question.id))
  conflict.value = false
  errorMessage.value = ''
}

// 从单题“加入材料题”进入：取出 URL 中的题目后立即移除参数，避免刷新重复加入。
const takeQueryQuestion = async (key: 'from_question' | 'add_question'): Promise<Question | null> => {
  const questionId = Number(route.query[key])
  if (!Number.isInteger(questionId) || questionId <= 0) return null
  await router.replace({ query: { ...route.query, [key]: undefined } })
  try {
    const question = await $api<Question>(`/questions/${questionId}`)
    if (question.stimulus_id != null && question.stimulus_id !== props.stimulusId) {
      errorMessage.value = t('stimuli.form.questionInOtherStimulus', { id: question.id, stimulusId: question.stimulus_id })
      return null
    }
    return question
  } catch (error) {
    errorMessage.value = getApiErrorDetail(error, t('stimuli.form.questionLoadFailed'))
    return null
  }
}

// 新建材料题：该题作为第 1 小题，材料题沿用它的状态与可见性。
const prefillFromQuestion = async () => {
  if (isEdit.value || !route.query.from_question) return
  loading.value = true
  try {
    const question = await takeQueryQuestion('from_question')
    if (!question) return
    status.value = question.status
    visibility.value = question.visibility
    entries.value = [entryFromQuestion(question as unknown as QuestionSummary)]
    resetBaseline([])
  } finally {
    loading.value = false
  }
}

// 已有材料题：追加到末尾，保持未保存状态让用户确认位置后再保存。
const appendRequestedQuestion = async () => {
  if (!route.query.add_question) return
  const question = await takeQueryQuestion('add_question')
  if (!question || selectedIds.value.includes(question.id)) return
  entries.value = addExisting(entries.value, [question as unknown as QuestionSummary])
  toast.info(t('stimuli.form.questionAppended', { id: question.id }))
  await nextTick()
  document.getElementById(`member-q-${question.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

const load = async (force = false) => {
  if (!isEdit.value || !props.stimulusId || !editorSubjectId.value || (dirty.value && !force)) return
  loading.value = true
  try {
    applyStimulus(await getStimulus(editorSubjectId.value, props.stimulusId))
  } catch (error) {
    errorMessage.value = getApiErrorDetail(error, t('materials.loadFailed'))
    return
  } finally {
    loading.value = false
  }
  await appendRequestedQuestion()
  await focusRequestedQuestion()
}

// 从题库「材料题 #id」进入时展开并定位到该小题。
const focusRequestedQuestion = async () => {
  const questionId = Number(route.query.focus)
  const entry = entries.value.find(item => item.id === questionId)
  if (!entry) return
  expanded.value = new Set([...expanded.value, entry.key])
  await nextTick()
  document.getElementById(`member-${entry.key}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

watch(currentSubjectId, (subjectId) => {
  if (editorSubjectId.value === null && subjectId !== null) {
    editorSubjectId.value = subjectId
    void load()
  }
}, { immediate: true })
onMounted(() => { void prefillFromQuestion() })

const restoreSubject = async () => {
  if (editorSubjectId.value !== null) await setSubject(editorSubjectId.value)
}

const beforeUnloadHandler = (event: BeforeUnloadEvent) => {
  if (dirty.value) {
    event.preventDefault()
    event.returnValue = ''
  }
}
onMounted(() => window.addEventListener('beforeunload', beforeUnloadHandler))
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnloadHandler))
onBeforeRouteLeave(() => !dirty.value || window.confirm(t('stimuli.form.leaveConfirm')))

const toggleExpanded = (key: string) => {
  const next = new Set(expanded.value)
  if (!next.delete(key)) next.add(key)
  expanded.value = next
}
const addNewQuestion = async () => {
  const entry = newEntry({ status: status.value, visibility: visibility.value })
  entries.value = [...entries.value, entry]
  expanded.value = new Set([...expanded.value, entry.key])
  await nextTick()
  document.getElementById(`member-${entry.key}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
const addQuestions = (questions: QuestionSummary[]) => {
  entries.value = addExisting(entries.value, questions)
}
const removeEntry = (entry: MemberEntry) => {
  const edited = entry.id == null ? !isEmptyRichDoc(entry.draft.content) : isBodyDirty(entry)
  const message = entry.id == null ? t('stimuli.form.deleteNewConfirm') : t('stimuli.form.removeDirtyConfirm')
  if (edited && !window.confirm(message)) return
  entries.value = entries.value.filter(item => item.key !== entry.key)
}
const moveQuestion = (from: number, to: number) => { entries.value = moveMember(entries.value, from, to) }

const validationMessage = (): string => {
  if (!editorSubjectId.value) return t('materials.selectSubjectFirst')
  if (subjectMismatch.value) return t('stimuli.form.switchBackSubjectFirst')
  if (!canEdit.value) return t('stimuli.form.noPermission')
  if (isEmptyRichDoc(content.value)) return t('stimuli.form.contentRequired')
  if (incompatibleMessage.value) return incompatibleMessage.value
  return validateMembers(entries.value, meta.value) ?? ''
}

// 材料、新建/修改的小题与顺序一次性整体保存，任一失败服务端整体回滚。
const submit = async () => {
  const invalid = validationMessage()
  if (invalid) {
    errorMessage.value = invalid
    return
  }
  const subjectId = editorSubjectId.value!
  saving.value = true
  conflict.value = false
  errorMessage.value = ''
  const payload = {
    content: content.value,
    status: status.value,
    visibility: visibility.value,
    source: source.value.trim(),
    questions: buildBundleQuestions(entries.value, meta.value),
  }
  try {
    const detail = props.stimulusId == null
      ? await createStimulusBundle(subjectId, payload)
      : await updateStimulusBundle(subjectId, props.stimulusId, { ...payload, expected_revision: revision.value! })
    applyStimulus(detail)
    toast.success(isEdit.value ? t('stimuli.form.saved') : t('stimuli.form.created'))
    if (!isEdit.value) await router.replace(`/materials/${detail.id}/edit`)
  } catch (error) {
    if (isRevisionConflict(error)) conflict.value = true
    else errorMessage.value = getApiErrorDetail(error, t('stimuli.form.saveFailed'))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="flex flex-1 flex-col">
    <header class="flex min-h-14 items-center justify-between gap-3 border-b px-4">
      <div class="flex items-center gap-2">
        <Button variant="ghost" size="icon" :title="t('stimuli.form.backToList')" :aria-label="t('stimuli.form.backToList')" @click="router.push('/materials')"><ArrowLeft class="size-4" /></Button>
        <h1 class="text-base font-semibold">{{ isEdit ? t('stimuli.form.editTitle') : t('materials.create') }}</h1>
      </div>
      <div class="flex items-center gap-2">
        <Button
          v-if="isEdit"
          variant="outline"
          :disabled="dirty || saved.questionIds.length === 0"
          :title="dirty ? t('stimuli.form.saveFirst') : t('stimuli.form.addToCompositionHint')"
          @click="compositionPickerOpen = true"
        >
          <FilePlus2 class="mr-2 size-4" />{{ t('stimuli.form.addToComposition') }}
        </Button>
        <Button :disabled="saving || loading || !canEdit || subjectMismatch || (isEdit && !dirty)" @click="submit"><Loader2 v-if="saving" class="mr-2 size-4 animate-spin" /><Save v-else class="mr-2 size-4" />{{ t('common.save') }}</Button>
        <AiPanelToggle />
      </div>
    </header>

    <main class="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-5 px-4 py-6">
      <Alert v-if="!currentSubjectId || !canEdit" variant="destructive"><AlertTriangle class="size-4" /><AlertTitle>{{ t('stimuli.form.cannotEdit') }}</AlertTitle><AlertDescription>{{ !currentSubjectId ? t('stimuli.form.selectSubjectFirstSentence') : t('stimuli.form.noPermissionSentence') }}</AlertDescription></Alert>
      <Alert v-if="subjectMismatch"><AlertTriangle class="size-4" /><AlertTitle>{{ t('stimuli.form.subjectSwitched') }}</AlertTitle><AlertDescription class="space-y-3"><p>{{ t('stimuli.form.subjectSwitchedDescription', { id: editorSubjectId }) }}</p><div class="flex flex-wrap gap-2"><Button size="sm" variant="outline" @click="restoreSubject">{{ t('stimuli.form.restoreSubject') }}</Button><Button size="sm" variant="ghost" @click="router.push('/materials')">{{ t('stimuli.form.backToList') }}</Button></div></AlertDescription></Alert>
      <Alert v-if="conflict" variant="destructive">
        <AlertTriangle class="size-4" /><AlertTitle>{{ t('stimuli.form.conflictTitle') }}</AlertTitle>
        <AlertDescription class="space-y-3"><p>{{ t('stimuli.form.conflictDescription') }}</p><div class="flex flex-wrap gap-2"><Button size="sm" variant="destructive" @click="load(true)">{{ t('stimuli.form.loadLatest') }}</Button><Button size="sm" variant="outline" @click="conflict = false">{{ t('stimuli.form.keepLocal') }}</Button></div></AlertDescription>
      </Alert>
      <Alert v-if="incompatible.length" variant="destructive"><AlertTriangle class="size-4" /><AlertTitle>{{ t('stimuli.form.incompatibleTitle') }}</AlertTitle><AlertDescription>{{ incompatibleMessage }}</AlertDescription></Alert>
      <Alert v-if="errorMessage" variant="destructive"><AlertTriangle class="size-4" /><AlertTitle>{{ t('common.operationFailed') }}</AlertTitle><AlertDescription>{{ errorMessage }}</AlertDescription></Alert>
      <p v-if="impactHint" class="text-sm text-muted-foreground" role="status">{{ impactHint }}</p>
      <div v-if="loading" class="flex justify-center py-20"><Loader2 class="size-7 animate-spin text-muted-foreground" /></div>
      <template v-else>
        <div class="space-y-2">
          <Label>{{ t('stimuli.form.material') }}</Label>
          <p class="text-xs text-muted-foreground">{{ t('stimuli.form.materialHint') }}</p>
          <RichEditor v-model="content" />
        </div>

        <section class="space-y-3">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 class="text-sm font-semibold">{{ t('stimuli.form.membersTitle', { count: entries.length }) }}</h2>
              <p class="text-xs text-muted-foreground">{{ t('stimuli.form.membersHint') }}</p>
            </div>
            <div class="flex gap-2">
              <Button size="sm" :disabled="!canEdit" @click="addNewQuestion"><Plus class="mr-2 size-4" />{{ t('stimuli.form.newMember') }}</Button>
              <DropdownMenu>
                <DropdownMenuTrigger as-child>
                  <Button variant="outline" size="icon" class="size-8" :disabled="!canEdit" :title="t('common.moreActions')" :aria-label="t('common.moreActions')"><Ellipsis class="size-4" /></Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem @click="pickerOpen = true"><ListPlus class="mr-2 size-4" />{{ t('stimuli.form.addExisting') }}</DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
          <draggable v-model="entries" item-key="key" handle=".drag-handle" class="divide-y border-y">
            <template #item="{ element: entry, index }">
              <article :id="`member-${entry.key}`" class="scroll-mt-20 py-3">
                <div class="flex items-start gap-2">
                  <button type="button" class="drag-handle mt-1 cursor-grab text-muted-foreground" :title="t('stimuli.form.dragToSort')" :aria-label="t('stimuli.form.dragToSort')"><GripVertical class="size-4" /></button>
                  <span class="mt-1 w-6 text-center text-xs text-muted-foreground">{{ index + 1 }}</span>
                  <div class="min-w-0 flex-1">
                    <div class="mb-1 flex flex-wrap gap-2">
                      <Badge v-if="entry.id == null" variant="default">{{ t('stimuli.form.newBadge') }}</Badge>
                      <Badge v-else variant="outline">#{{ entry.id }}</Badge>
                      <Badge variant="secondary">{{ questionTypeDisplayLabel(entry.draft.q_type) }}</Badge>
                      <Badge variant="outline">{{ t(STATUS_KEYS[effectiveMeta(entry, meta).status]) }}</Badge>
                      <Badge v-if="effectiveMeta(entry, meta).visibility === 'private'" variant="outline">{{ t('materials.filters.private') }}</Badge>
                      <Badge v-if="entry.id != null && isBodyDirty(entry)" variant="outline" class="border-amber-500/50 text-amber-700 dark:text-amber-400">{{ t('stimuli.form.modified') }}</Badge>
                      <Badge v-if="incompatible.includes(index + 1)" variant="destructive">{{ t('stimuli.form.incompatibleBadge') }}</Badge>
                    </div>
                    <button v-if="!expanded.has(entry.key)" type="button" class="block w-full text-left" @click="toggleExpanded(entry.key)">
                      <RichContent :content="entry.draft.content" :empty-text="t('stimuli.form.emptyStem')" class="line-clamp-3 text-sm" />
                    </button>
                  </div>
                  <div class="flex shrink-0">
                    <Button variant="ghost" size="icon" :title="expanded.has(entry.key) ? t('stimuli.form.collapse') : t('common.edit')" :aria-label="expanded.has(entry.key) ? t('stimuli.form.collapse') : t('common.edit')" @click="toggleExpanded(entry.key)">
                      <ChevronUp v-if="expanded.has(entry.key)" class="size-4" /><Pencil v-else class="size-4" />
                    </Button>
                    <Button variant="ghost" size="icon" :disabled="index === 0" :title="t('stimuli.form.moveUp')" :aria-label="t('stimuli.form.moveUp')" @click="moveQuestion(index, index - 1)"><ArrowUp class="size-4" /></Button>
                    <Button variant="ghost" size="icon" :disabled="index === entries.length - 1" :title="t('stimuli.form.moveDown')" :aria-label="t('stimuli.form.moveDown')" @click="moveQuestion(index, index + 1)"><ArrowDown class="size-4" /></Button>
                    <Button v-if="entry.id == null" variant="ghost" size="icon" class="text-destructive" :title="t('stimuli.form.deleteMember')" :aria-label="t('stimuli.form.deleteMember')" @click="removeEntry(entry)"><Trash2 class="size-4" /></Button>
                    <Button v-else variant="ghost" size="icon" :title="t('stimuli.form.detachMember')" :aria-label="t('stimuli.form.detachMember')" @click="removeEntry(entry)"><Unlink class="size-4" /></Button>
                  </div>
                </div>
                <div v-if="expanded.has(entry.key)" class="mt-3 ml-8 border-l-2 pl-4">
                  <QuestionDraftEditor :model-value="entry.draft" />
                  <div class="mt-4 flex justify-end">
                    <Button variant="outline" size="sm" @click="toggleExpanded(entry.key)"><ChevronUp class="mr-2 size-4" />{{ t('stimuli.form.collapse') }}</Button>
                  </div>
                </div>
              </article>
            </template>
          </draggable>
          <p v-if="entries.length === 0" class="border border-dashed py-12 text-center text-sm text-muted-foreground">{{ t('stimuli.form.emptyMembers') }}</p>
          <Button v-if="entries.length > 0" variant="outline" class="w-full border-dashed" :disabled="!canEdit" @click="addNewQuestion"><Plus class="mr-2 size-4" />{{ t('stimuli.form.newMember') }}</Button>
        </section>

        <Collapsible v-model:open="settingsOpen" class="border-t pt-4">
          <CollapsibleTrigger as-child>
            <button type="button" class="flex w-full items-center gap-2 text-left text-sm">
              <ChevronDown class="size-4 shrink-0 text-muted-foreground transition-transform" :class="settingsOpen ? '' : '-rotate-90'" />
              <span class="font-semibold">{{ t('stimuli.form.settings') }}</span>
              <span class="truncate text-xs text-muted-foreground">{{ settingsSummary }}</span>
            </button>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div class="mt-3 grid gap-4 bg-muted/40 p-4 sm:grid-cols-3">
              <div class="space-y-2"><Label>{{ t('materials.filters.status') }}</Label><Select v-model="status"><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem v-for="(key, value) in STATUS_KEYS" :key="value" :value="value">{{ t(key) }}</SelectItem></SelectContent></Select></div>
              <div class="space-y-2"><Label>{{ t('materials.filters.visibility') }}</Label><Select v-model="visibility"><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="public">{{ t('materials.filters.public') }}</SelectItem><SelectItem value="private">{{ t('materials.filters.private') }}</SelectItem></SelectContent></Select></div>
              <div class="space-y-2"><Label for="stimulus-source">{{ t('stimuli.form.source') }}</Label><Input id="stimulus-source" v-model="source" :placeholder="t('stimuli.form.optional')" /></div>
            </div>
          </CollapsibleContent>
        </Collapsible>
      </template>
    </main>
  </div>

  <StimulusQuestionPickerDialog v-model:open="pickerOpen" :subject-id="editorSubjectId" :selected-ids="selectedIds" :stimulus-visibility="visibility" @select="addQuestions" />
  <CompositionTargetPicker v-model:open="compositionPickerOpen" :subject-id="editorSubjectId" :question-ids="saved.questionIds" />
</template>
