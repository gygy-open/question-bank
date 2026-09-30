<script setup lang="ts">
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
import { questionTypeLabel } from '@/lib/answerFormat'
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
  ? `私有材料题下不能包含公开小题（第 ${incompatible.value.join('、')} 小题）。请移出这些小题，或在“设置”中把材料题改为公开。`
  : '')
const settingsOpen = ref(false)
// 冲突提示要求改可见性时，把设置区展开到用户眼前。
watch(incompatible, (items) => { if (items.length) settingsOpen.value = true })
const STATUS_LABELS: Record<QuestionStatus, string> = { draft: '草稿', pending: '待审核', published: '已发布', archived: '已归档' }
const settingsSummary = computed(() =>
  [STATUS_LABELS[status.value], visibility.value === 'private' ? '私有' : '公开', source.value.trim()].filter(Boolean).join(' · '))

const resetBaseline = (questionIds: number[]) => {
  saved.value = { status: status.value, visibility: visibility.value, snapshot: snapshot.value, questionIds }
}

const applyStimulus = (stimulus: StimulusDetail) => {
  content.value = structuredClone(stimulus.content)
  status.value = stimulus.status
  visibility.value = stimulus.visibility
  source.value = stimulus.source ?? ''
  revision.value = stimulus.revision
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
      errorMessage.value = `题目 #${question.id} 已属于材料题 #${question.stimulus_id}，需先从原材料题移出。`
      return null
    }
    return question
  } catch (error) {
    errorMessage.value = getApiErrorDetail(error, '题目加载失败')
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
  toast.info(`已把题目 #${question.id} 加到末尾，保存后生效`)
  await nextTick()
  document.getElementById(`member-q-${question.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

const load = async (force = false) => {
  if (!isEdit.value || !props.stimulusId || !editorSubjectId.value || (dirty.value && !force)) return
  loading.value = true
  try {
    applyStimulus(await getStimulus(editorSubjectId.value, props.stimulusId))
  } catch (error) {
    errorMessage.value = getApiErrorDetail(error, '材料题加载失败')
    return
  } finally {
    loading.value = false
  }
  await appendRequestedQuestion()
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
onBeforeRouteLeave(() => !dirty.value || window.confirm('材料题有未保存的修改，确定要离开吗？'))

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
  const message = entry.id == null ? '删除这道未保存的小题？' : '这道小题的未保存修改将丢失，确定移出吗？'
  if (edited && !window.confirm(message)) return
  entries.value = entries.value.filter(item => item.key !== entry.key)
}
const moveQuestion = (from: number, to: number) => { entries.value = moveMember(entries.value, from, to) }

const validationMessage = (): string => {
  if (!editorSubjectId.value) return '请先选择学科'
  if (subjectMismatch.value) return '请先切回草稿所属学科'
  if (!canEdit.value) return '你没有编辑该学科材料题的权限'
  if (isEmptyRichDoc(content.value)) return '请填写材料内容'
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
    toast.success(isEdit.value ? '材料题已保存' : '材料题已创建')
    if (!isEdit.value) await router.replace(`/materials/${detail.id}/edit`)
  } catch (error) {
    if (isRevisionConflict(error)) conflict.value = true
    else errorMessage.value = getApiErrorDetail(error, '保存材料题失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="flex flex-1 flex-col">
    <header class="flex min-h-14 items-center justify-between gap-3 border-b px-4">
      <div class="flex items-center gap-2">
        <Button variant="ghost" size="icon" title="返回材料题列表" aria-label="返回材料题列表" @click="router.push('/materials')"><ArrowLeft class="size-4" /></Button>
        <h1 class="text-base font-semibold">{{ isEdit ? '编辑材料题' : '新建材料题' }}</h1>
      </div>
      <div class="flex items-center gap-2">
        <Button
          v-if="isEdit"
          variant="outline"
          :disabled="dirty || saved.questionIds.length === 0"
          :title="dirty ? '请先保存修改' : '把材料和全部小题作为一道材料题加入稿件'"
          @click="compositionPickerOpen = true"
        >
          <FilePlus2 class="mr-2 size-4" />加入稿件
        </Button>
        <Button :disabled="saving || loading || !canEdit || subjectMismatch || (isEdit && !dirty)" @click="submit"><Loader2 v-if="saving" class="mr-2 size-4 animate-spin" /><Save v-else class="mr-2 size-4" />保存</Button>
      </div>
    </header>

    <main class="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-5 px-4 py-6">
      <Alert v-if="!currentSubjectId || !canEdit" variant="destructive"><AlertTriangle class="size-4" /><AlertTitle>无法编辑</AlertTitle><AlertDescription>{{ !currentSubjectId ? '请先选择学科。' : '你没有编辑该学科材料题的权限。' }}</AlertDescription></Alert>
      <Alert v-if="subjectMismatch"><AlertTriangle class="size-4" /><AlertTitle>当前学科已切换</AlertTitle><AlertDescription class="space-y-3"><p>本地草稿仍属于学科 #{{ editorSubjectId }}，未被重新加载或覆盖。请切回原学科后继续保存，或返回列表放弃草稿。</p><div class="flex flex-wrap gap-2"><Button size="sm" variant="outline" @click="restoreSubject">切回原学科</Button><Button size="sm" variant="ghost" @click="router.push('/materials')">返回材料题列表</Button></div></AlertDescription></Alert>
      <Alert v-if="conflict" variant="destructive">
        <AlertTriangle class="size-4" /><AlertTitle>材料题已被其他人修改</AlertTitle>
        <AlertDescription class="space-y-3"><p>你的本地内容与小题顺序仍然保留。可以加载服务器最新版本，或继续编辑本地草稿后再决定。</p><div class="flex flex-wrap gap-2"><Button size="sm" variant="destructive" @click="load(true)">加载最新并放弃本地</Button><Button size="sm" variant="outline" @click="conflict = false">继续编辑本地</Button></div></AlertDescription>
      </Alert>
      <Alert v-if="incompatible.length" variant="destructive"><AlertTriangle class="size-4" /><AlertTitle>私有材料题下有公开小题</AlertTitle><AlertDescription>{{ incompatibleMessage }}</AlertDescription></Alert>
      <Alert v-if="errorMessage" variant="destructive"><AlertTriangle class="size-4" /><AlertTitle>操作失败</AlertTitle><AlertDescription>{{ errorMessage }}</AlertDescription></Alert>
      <div v-if="loading" class="flex justify-center py-20"><Loader2 class="size-7 animate-spin text-muted-foreground" /></div>
      <template v-else>
        <div class="space-y-2">
          <Label>材料</Label>
          <p class="text-xs text-muted-foreground">文章、图表或背景内容，小题围绕它作答。可以先只写材料，稍后再出题。</p>
          <RichEditor v-model="content" />
        </div>

        <section class="space-y-3">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 class="text-sm font-semibold">小题（{{ entries.length }}）</h2>
              <p class="text-xs text-muted-foreground">按此顺序出现在稿件中；移出后保留为单题。小题与材料一起保存。</p>
            </div>
            <div class="flex gap-2">
              <Button size="sm" :disabled="!canEdit" @click="addNewQuestion"><Plus class="mr-2 size-4" />新建小题</Button>
              <DropdownMenu>
                <DropdownMenuTrigger as-child>
                  <Button variant="outline" size="icon" class="size-8" :disabled="!canEdit" title="更多" aria-label="更多"><Ellipsis class="size-4" /></Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem @click="pickerOpen = true"><ListPlus class="mr-2 size-4" />从题库添加已有单题…</DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
          <draggable v-model="entries" item-key="key" handle=".drag-handle" class="divide-y border-y">
            <template #item="{ element: entry, index }">
              <article :id="`member-${entry.key}`" class="scroll-mt-20 py-3">
                <div class="flex items-start gap-2">
                  <button type="button" class="drag-handle mt-1 cursor-grab text-muted-foreground" title="拖动排序" aria-label="拖动排序"><GripVertical class="size-4" /></button>
                  <span class="mt-1 w-6 text-center text-xs text-muted-foreground">{{ index + 1 }}</span>
                  <div class="min-w-0 flex-1">
                    <div class="mb-1 flex flex-wrap gap-2">
                      <Badge v-if="entry.id == null" variant="default">新</Badge>
                      <Badge v-else variant="outline">#{{ entry.id }}</Badge>
                      <Badge variant="secondary">{{ questionTypeLabel(entry.draft.q_type) }}</Badge>
                      <Badge variant="outline">{{ STATUS_LABELS[effectiveMeta(entry, meta).status] }}</Badge>
                      <Badge v-if="effectiveMeta(entry, meta).visibility === 'private'" variant="outline">私有</Badge>
                      <Badge v-if="entry.id != null && isBodyDirty(entry)" variant="outline" class="border-amber-500/50 text-amber-700 dark:text-amber-400">已修改</Badge>
                      <Badge v-if="incompatible.includes(index + 1)" variant="destructive">公开小题不能放在私有材料题下</Badge>
                    </div>
                    <button v-if="!expanded.has(entry.key)" type="button" class="block w-full text-left" @click="toggleExpanded(entry.key)">
                      <RichContent :content="entry.draft.content" empty-text="（未填写题干）" class="line-clamp-3 text-sm" />
                    </button>
                  </div>
                  <div class="flex shrink-0">
                    <Button variant="ghost" size="icon" :title="expanded.has(entry.key) ? '收起' : '编辑'" :aria-label="expanded.has(entry.key) ? '收起' : '编辑'" @click="toggleExpanded(entry.key)">
                      <ChevronUp v-if="expanded.has(entry.key)" class="size-4" /><Pencil v-else class="size-4" />
                    </Button>
                    <Button variant="ghost" size="icon" :disabled="index === 0" title="上移" aria-label="上移" @click="moveQuestion(index, index - 1)"><ArrowUp class="size-4" /></Button>
                    <Button variant="ghost" size="icon" :disabled="index === entries.length - 1" title="下移" aria-label="下移" @click="moveQuestion(index, index + 1)"><ArrowDown class="size-4" /></Button>
                    <Button v-if="entry.id == null" variant="ghost" size="icon" class="text-destructive" title="删除此小题" aria-label="删除此小题" @click="removeEntry(entry)"><Trash2 class="size-4" /></Button>
                    <Button v-else variant="ghost" size="icon" title="移出（保留为单题）" aria-label="移出（保留为单题）" @click="removeEntry(entry)"><Unlink class="size-4" /></Button>
                  </div>
                </div>
                <div v-if="expanded.has(entry.key)" class="mt-3 ml-8 border-l-2 pl-4">
                  <QuestionDraftEditor :model-value="entry.draft" />
                  <div class="mt-4 flex justify-end">
                    <Button variant="outline" size="sm" @click="toggleExpanded(entry.key)"><ChevronUp class="mr-2 size-4" />收起</Button>
                  </div>
                </div>
              </article>
            </template>
          </draggable>
          <p v-if="entries.length === 0" class="border border-dashed py-12 text-center text-sm text-muted-foreground">还没有小题。点击“新建小题”开始出题；也可以先保存材料，稍后再出题。</p>
          <Button v-if="entries.length > 0" variant="outline" class="w-full border-dashed" :disabled="!canEdit" @click="addNewQuestion"><Plus class="mr-2 size-4" />新建小题</Button>
        </section>

        <Collapsible v-model:open="settingsOpen" class="border-t pt-4">
          <CollapsibleTrigger as-child>
            <button type="button" class="flex w-full items-center gap-2 text-left text-sm">
              <ChevronDown class="size-4 shrink-0 text-muted-foreground transition-transform" :class="settingsOpen ? '' : '-rotate-90'" />
              <span class="font-semibold">设置</span>
              <span class="truncate text-xs text-muted-foreground">{{ settingsSummary }}</span>
            </button>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div class="mt-3 grid gap-4 bg-muted/40 p-4 sm:grid-cols-3">
              <div class="space-y-2"><Label>状态</Label><Select v-model="status"><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="draft">草稿</SelectItem><SelectItem value="pending">待审核</SelectItem><SelectItem value="published">已发布</SelectItem><SelectItem value="archived">已归档</SelectItem></SelectContent></Select></div>
              <div class="space-y-2"><Label>可见性</Label><Select v-model="visibility"><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="public">公开</SelectItem><SelectItem value="private">私有</SelectItem></SelectContent></Select></div>
              <div class="space-y-2"><Label for="stimulus-source">来源</Label><Input id="stimulus-source" v-model="source" placeholder="可选" /></div>
            </div>
          </CollapsibleContent>
        </Collapsible>
      </template>
    </main>
  </div>

  <StimulusQuestionPickerDialog v-model:open="pickerOpen" :subject-id="editorSubjectId" :selected-ids="selectedIds" :stimulus-visibility="visibility" @select="addQuestions" />
  <CompositionTargetPicker v-model:open="compositionPickerOpen" :subject-id="editorSubjectId" :question-ids="saved.questionIds" />
</template>
