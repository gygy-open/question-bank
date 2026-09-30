<script setup lang="ts">
import { computed, nextTick, onActivated, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import draggable from 'vuedraggable'
import { AlertTriangle, ArrowDown, ArrowLeft, ArrowUp, FilePlus2, GripVertical, Loader2, Plus, Save, Unlink } from '@lucide/vue'
import { toast } from 'vue-sonner'
import StimulusQuestionPickerDialog from '@/components/stimuli/StimulusQuestionPickerDialog.vue'
import QuestionEditDialog from '@/components/QuestionEditDialog.vue'
import CompositionTargetPicker from '@/components/CompositionTargetPicker.vue'
import RichContent from '@/components/rich-editor/RichContent.vue'
import RichEditor from '@/components/rich-editor/RichEditor.vue'
import { isEmptyRichDoc } from '@/components/rich-editor/richDoc'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { questionTypeLabel } from '@/lib/answerFormat'
import { getApiErrorDetail, isRevisionConflict } from '@/lib/apiErrors'
import {
  addMember,
  hasEditorSubjectMismatch,
  moveMember,
  publicQuestionsUnderPrivateStimulus,
  removeMember,
  sameOrder,
} from '@/lib/stimulusEditor'
import type { Question, QuestionStatus, QuestionSummary, RichDoc, StimulusDetail } from '@/types'

const props = defineProps<{ stimulusId?: number }>()
const router = useRouter()
const { currentSubjectId, setSubject } = useSubjectContext()
const { can } = usePermissions()
const { createStimulus, getStimulus, updateStimulus, setStimulusQuestions } = useStimuli()
const editorSubjectId = ref<number | null>(null)
// 新建材料后若保存小题失败，重试应更新这份材料而不是再建一份。
const createdId = ref<number | null>(null)
const stimulusId = computed(() => props.stimulusId ?? createdId.value)
const canEdit = computed(() => can(Capability.EDIT_QUESTION, editorSubjectId.value))
const isEdit = computed(() => props.stimulusId != null)
const subjectMismatch = computed(() => hasEditorSubjectMismatch(editorSubjectId.value, currentSubjectId.value))

const content = ref<RichDoc>(null)
const status = ref<QuestionStatus>('draft')
const visibility = ref<'public' | 'private'>('public')
const source = ref('')
const revision = ref<number | null>(null)
const members = ref<QuestionSummary[]>([])
const savedMembers = ref<QuestionSummary[]>([])
const loading = ref(false)
const saving = ref(false)
const metaDirty = ref(false)
const hydrating = ref(false)
const conflict = ref(false)
const errorMessage = ref('')
const pickerOpen = ref(false)
const createOpen = ref(false)
const compositionPickerOpen = ref(false)

const membersDirty = computed(() => !sameOrder(members.value, savedMembers.value))
const dirty = computed(() => metaDirty.value || membersDirty.value)
const selectedIds = computed(() => members.value.map(member => member.id))
const incompatibleIds = computed(() => publicQuestionsUnderPrivateStimulus(visibility.value, members.value))

const applyStimulus = (stimulus: StimulusDetail) => {
  content.value = structuredClone(stimulus.content)
  status.value = stimulus.status
  visibility.value = stimulus.visibility
  source.value = stimulus.source ?? ''
  revision.value = stimulus.revision
  members.value = stimulus.questions.slice()
  savedMembers.value = stimulus.questions.slice()
  metaDirty.value = false
  conflict.value = false
  errorMessage.value = ''
}

const load = async (force = false) => {
  if (!isEdit.value || !props.stimulusId || !editorSubjectId.value || (dirty.value && !force)) return
  loading.value = true
  hydrating.value = true
  try {
    applyStimulus(await getStimulus(editorSubjectId.value, props.stimulusId))
  } catch (error) {
    errorMessage.value = getApiErrorDetail(error, '题目材料加载失败')
  } finally {
    loading.value = false
    await nextTick()
    metaDirty.value = false
    hydrating.value = false
  }
}

watch([content, status, visibility, source], () => { if (!hydrating.value) metaDirty.value = true }, { deep: true })
watch(currentSubjectId, (subjectId) => {
  if (editorSubjectId.value === null && subjectId !== null) {
    editorSubjectId.value = subjectId
    void load()
  }
}, { immediate: true })
onActivated(() => load(false))

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
onBeforeRouteLeave(() => !dirty.value || window.confirm('题目材料有未保存的修改，确定要离开吗？'))

const addQuestions = (questions: QuestionSummary[]) => {
  members.value = questions.reduce((current, question) => addMember(current, question), members.value)
}
const addCreatedQuestion = (question: Question) => {
  addQuestions([question as unknown as QuestionSummary])
  createOpen.value = false
}
const detachQuestion = (questionId: number) => { members.value = removeMember(members.value, questionId) }
const moveQuestion = (from: number, to: number) => { members.value = moveMember(members.value, from, to) }

const validationMessage = (): string => {
  if (!editorSubjectId.value) return '请先选择学科'
  if (subjectMismatch.value) return '请先切回草稿所属学科'
  if (!canEdit.value) return '你没有编辑该学科题目材料的权限'
  if (isEmptyRichDoc(content.value)) return '请填写题目材料内容'
  if (incompatibleIds.value.length) {
    return `私有题目材料下不能挂公开题目（${incompatibleIds.value.map(id => `#${id}`).join('、')}）。请移出这些小题，或把题目材料改为公开。`
  }
  return ''
}

// 正文/元数据与小题成员走两条接口；共用同一乐观锁，先存正文再用新 revision 存成员。
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
  const payload = { content: content.value, status: status.value, visibility: visibility.value, source: source.value.trim() || null }
  try {
    let currentRevision = revision.value
    if (stimulusId.value == null) {
      const created = await createStimulus(subjectId, payload)
      createdId.value = created.id
      currentRevision = created.revision
    } else if (metaDirty.value && currentRevision) {
      currentRevision = (await updateStimulus(subjectId, stimulusId.value, { ...payload, expected_revision: currentRevision })).revision
    }
    metaDirty.value = false
    revision.value = currentRevision
    if (stimulusId.value != null && currentRevision && membersDirty.value) {
      const detail = await setStimulusQuestions(subjectId, stimulusId.value, {
        expected_revision: currentRevision,
        question_ids: members.value.map(member => member.id),
      })
      revision.value = detail.revision
      savedMembers.value = detail.questions.slice()
      members.value = detail.questions.slice()
    }
    toast.success(isEdit.value ? '题目材料已保存' : '题目材料已创建')
    if (!isEdit.value && createdId.value != null) await router.push(`/materials/${createdId.value}/edit`)
  } catch (error) {
    if (isRevisionConflict(error)) conflict.value = true
    else errorMessage.value = getApiErrorDetail(error, '保存题目材料失败')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="flex flex-1 flex-col">
    <header class="flex min-h-14 items-center justify-between gap-3 border-b px-4">
      <div class="flex items-center gap-2">
        <Button variant="ghost" size="icon" title="返回题目材料列表" aria-label="返回题目材料列表" @click="router.push('/materials')"><ArrowLeft class="size-4" /></Button>
        <h1 class="text-base font-semibold">{{ isEdit ? '编辑题目材料' : '创建题目材料' }}</h1>
      </div>
      <div class="flex items-center gap-2">
        <Button
          v-if="isEdit"
          variant="outline"
          :disabled="dirty || savedMembers.length === 0"
          :title="dirty ? '请先保存修改' : '把材料和全部小题作为一道材料题加入稿件'"
          @click="compositionPickerOpen = true"
        >
          <FilePlus2 class="mr-2 size-4" />加入稿件
        </Button>
        <Button :disabled="saving || loading || !canEdit || subjectMismatch || (stimulusId != null && !dirty)" @click="submit"><Loader2 v-if="saving" class="mr-2 size-4 animate-spin" /><Save v-else class="mr-2 size-4" />保存</Button>
      </div>
    </header>

    <main class="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-5 px-4 py-6">
      <Alert v-if="!currentSubjectId || !canEdit" variant="destructive"><AlertTriangle class="size-4" /><AlertTitle>无法编辑</AlertTitle><AlertDescription>{{ !currentSubjectId ? '请先选择学科。' : '你没有编辑该学科题目材料的权限。' }}</AlertDescription></Alert>
      <Alert v-if="subjectMismatch"><AlertTriangle class="size-4" /><AlertTitle>当前学科已切换</AlertTitle><AlertDescription class="space-y-3"><p>本地草稿仍属于学科 #{{ editorSubjectId }}，未被重新加载或覆盖。请切回原学科后继续保存，或返回列表放弃草稿。</p><div class="flex flex-wrap gap-2"><Button size="sm" variant="outline" @click="restoreSubject">切回原学科</Button><Button size="sm" variant="ghost" @click="router.push('/materials')">返回题目材料列表</Button></div></AlertDescription></Alert>
      <Alert v-if="conflict" variant="destructive">
        <AlertTriangle class="size-4" /><AlertTitle>题目材料已被其他人修改</AlertTitle>
        <AlertDescription class="space-y-3"><p>你的本地内容与小题顺序仍然保留。可以加载服务器最新版本，或继续编辑本地草稿后再决定。</p><div class="flex flex-wrap gap-2"><Button size="sm" variant="destructive" @click="load(true)">加载最新并放弃本地</Button><Button size="sm" variant="outline" @click="conflict = false">继续编辑本地</Button></div></AlertDescription>
      </Alert>
      <Alert v-if="incompatibleIds.length" variant="destructive"><AlertTriangle class="size-4" /><AlertTitle>私有题目材料下有公开小题</AlertTitle><AlertDescription>{{ validationMessage() }}</AlertDescription></Alert>
      <Alert v-if="errorMessage" variant="destructive"><AlertTriangle class="size-4" /><AlertTitle>操作失败</AlertTitle><AlertDescription>{{ errorMessage }}</AlertDescription></Alert>
      <div v-if="loading" class="flex justify-center py-20"><Loader2 class="size-7 animate-spin text-muted-foreground" /></div>
      <template v-else>
        <div class="grid gap-4 bg-muted/40 p-4 sm:grid-cols-3">
          <div class="space-y-2"><Label>状态</Label><Select v-model="status"><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="draft">草稿</SelectItem><SelectItem value="pending">待审核</SelectItem><SelectItem value="published">已发布</SelectItem><SelectItem value="archived">已归档</SelectItem></SelectContent></Select></div>
          <div class="space-y-2"><Label>可见性</Label><Select v-model="visibility"><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="public">公开</SelectItem><SelectItem value="private">私有</SelectItem></SelectContent></Select></div>
          <div class="space-y-2"><Label for="stimulus-source">来源</Label><Input id="stimulus-source" v-model="source" placeholder="可选" /></div>
        </div>
        <div class="space-y-2"><Label>题目材料内容</Label><RichEditor v-model="content" /></div>

        <section class="space-y-3">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 class="text-sm font-semibold">小题（{{ members.length }}）</h2>
              <p class="text-xs text-muted-foreground">小题依赖本材料作答，按此顺序出现在稿件中；移出材料后题目保留为独立题。</p>
            </div>
            <div class="flex gap-2">
              <Button variant="outline" size="sm" :disabled="!canEdit" @click="createOpen = true"><Plus class="mr-2 size-4" />新建小题</Button>
              <Button size="sm" :disabled="!canEdit" @click="pickerOpen = true"><Plus class="mr-2 size-4" />添加已有题目</Button>
            </div>
          </div>
          <draggable v-model="members" item-key="id" handle=".drag-handle" class="divide-y border-y">
            <template #item="{ element: member, index }">
              <article class="flex items-start gap-2 py-3">
                <button type="button" class="drag-handle mt-1 cursor-grab text-muted-foreground" title="拖动排序" aria-label="拖动排序"><GripVertical class="size-4" /></button>
                <span class="mt-1 w-6 text-center text-xs text-muted-foreground">{{ index + 1 }}</span>
                <div class="min-w-0 flex-1">
                  <div class="mb-1 flex flex-wrap gap-2">
                    <Badge variant="outline">#{{ member.id }}</Badge>
                    <Badge variant="secondary">{{ questionTypeLabel(member.q_type) }}</Badge>
                    <Badge variant="outline">{{ member.status }}</Badge>
                    <Badge v-if="member.visibility === 'private'" variant="outline">私有</Badge>
                    <Badge v-if="incompatibleIds.includes(member.id)" variant="destructive">公开题不能挂私有材料</Badge>
                  </div>
                  <RichContent :content="member.content" class="line-clamp-3 text-sm" />
                </div>
                <div class="flex shrink-0">
                  <Button variant="ghost" size="icon" :disabled="index === 0" title="上移" aria-label="上移" @click="moveQuestion(index, index - 1)"><ArrowUp class="size-4" /></Button>
                  <Button variant="ghost" size="icon" :disabled="index === members.length - 1" title="下移" aria-label="下移" @click="moveQuestion(index, index + 1)"><ArrowDown class="size-4" /></Button>
                  <Button variant="ghost" size="icon" title="移出材料（保留为独立题）" aria-label="移出材料" @click="detachQuestion(member.id)"><Unlink class="size-4" /></Button>
                </div>
              </article>
            </template>
          </draggable>
          <p v-if="members.length === 0" class="border border-dashed py-12 text-center text-sm text-muted-foreground">尚无小题。可以新建小题，或把已有的独立题添加到本材料下。</p>
        </section>
      </template>
    </main>
  </div>

  <StimulusQuestionPickerDialog v-model:open="pickerOpen" :subject-id="editorSubjectId" :selected-ids="selectedIds" :stimulus-visibility="visibility" @select="addQuestions" />
  <QuestionEditDialog v-model:open="createOpen" mode="create" :auto-fill-subject-id="editorSubjectId" @success="addCreatedQuestion" />
  <CompositionTargetPicker v-model:open="compositionPickerOpen" :subject-id="editorSubjectId" :question-ids="savedMembers.map(member => member.id)" />
</template>
