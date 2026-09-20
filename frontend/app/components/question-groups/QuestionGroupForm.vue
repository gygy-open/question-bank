<script setup lang="ts">
import { computed, nextTick, onActivated, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import draggable from 'vuedraggable'
import { AlertTriangle, ArrowDown, ArrowLeft, ArrowUp, FilePenLine, GripVertical, Loader2, Plus, Save, Search, Trash2 } from '@lucide/vue'
import { toast } from 'vue-sonner'
import MaterialPickerDialog from '@/components/materials/MaterialPickerDialog.vue'
import QuestionPickerDialog from '@/components/question-groups/QuestionPickerDialog.vue'
import QuestionEditDialog from '@/components/QuestionEditDialog.vue'
import RichContent from '@/components/rich-editor/RichContent.vue'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { questionTypeLabel } from '@/lib/answerFormat'
import { addMember, getApiErrorDetail, getPublicGroupCompatibility, hasEditorSubjectMismatch, isRevisionConflict, moveMember, normalizeMembers, removeMember, sortAndNormalizeMembers, type OrderedQuestionMember } from '@/lib/questionGroupEditor'
import type { Question, QuestionStatus, QuestionSummary, Stimulus } from '@/types'

const props = defineProps<{ groupId?: number }>()
const router = useRouter()
const { currentSubjectId, setSubject } = useSubjectContext()
const { can } = usePermissions()
const { getQuestionGroup, createQuestionGroup, updateQuestionGroup } = useQuestionGroups()
const editorSubjectId = ref<number | null>(null)
const canEdit = computed(() => can(Capability.EDIT_QUESTION, editorSubjectId.value))
const isEdit = computed(() => props.groupId != null)
const subjectMismatch = computed(() => hasEditorSubjectMismatch(editorSubjectId.value, currentSubjectId.value))

const selectedMaterial = ref<Stimulus | null>(null)
const members = ref<OrderedQuestionMember[]>([])
const status = ref<QuestionStatus>('draft')
const visibility = ref<'public' | 'private'>('public')
const source = ref('')
const revision = ref<number | null>(null)
const loading = ref(false)
const saving = ref(false)
const dirty = ref(false)
const hydrating = ref(false)
const conflict = ref(false)
const errorMessage = ref('')
const materialPickerOpen = ref(false)
const questionPickerOpen = ref(false)
const questionCreateOpen = ref(false)
const selectedIds = computed(() => members.value.map(member => member.question_id))
const compatibility = computed(() => getPublicGroupCompatibility(visibility.value, selectedMaterial.value, members.value))
const incompatible = computed(() => compatibility.value.privateMaterial || compatibility.value.privateQuestionIds.length > 0)
const compatibilityMessage = computed(() => {
  const issues: string[] = []
  if (compatibility.value.privateMaterial) issues.push('所选题目材料为私有题目材料')
  if (compatibility.value.privateQuestionIds.length > 0) issues.push(`私有题目：${compatibility.value.privateQuestionIds.map(id => `#${id}`).join('、')}`)
  return `公开题组不能引用私有资源（${issues.join('；')}）。请移除这些资源，或将题组改为私有。`
})

const finishHydration = async () => { await nextTick(); dirty.value = false; hydrating.value = false }
const load = async (force = false) => {
  if (!isEdit.value || !props.groupId || !editorSubjectId.value || (dirty.value && !force)) return
  loading.value = true
  hydrating.value = true
  try {
    const group = await getQuestionGroup(editorSubjectId.value, props.groupId)
    selectedMaterial.value = structuredClone(group.stimulus)
    members.value = sortAndNormalizeMembers(group.items)
    status.value = group.status
    visibility.value = group.visibility
    source.value = group.source ?? ''
    revision.value = group.revision
    conflict.value = false
    errorMessage.value = ''
  } catch (error) {
    errorMessage.value = getApiErrorDetail(error, '题组加载失败')
  } finally {
    loading.value = false
    await finishHydration()
  }
}
watch([selectedMaterial, members, status, visibility, source], () => { if (!hydrating.value) dirty.value = true }, { deep: true })
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
onBeforeRouteLeave(() => !dirty.value || window.confirm('题组有未保存的修改，确定要离开吗？'))

const selectMaterial = (material: Stimulus) => { selectedMaterial.value = material }
const addQuestions = (questions: QuestionSummary[]) => {
  members.value = questions.reduce((current, question) => addMember(current, question), members.value)
}
const addCreatedQuestion = (question: Question) => { addQuestions([question]); questionCreateOpen.value = false }
const removeQuestion = (questionId: number) => { members.value = removeMember(members.value, questionId) }
const moveQuestion = (from: number, to: number) => { members.value = moveMember(members.value, from, to) }
const normalizeAfterDrag = () => { members.value = normalizeMembers(members.value) }

const submit = async () => {
  if (!editorSubjectId.value || subjectMismatch.value || !canEdit.value || !selectedMaterial.value || members.value.length === 0 || incompatible.value) {
    errorMessage.value = !editorSubjectId.value ? '请先选择学科' : subjectMismatch.value ? '请先切回草稿所属学科' : !canEdit.value ? '你没有编辑该学科题组的权限' : !selectedMaterial.value ? '请选择题目材料' : members.value.length === 0 ? '题组至少包含一道题' : compatibilityMessage.value
    return
  }
  saving.value = true
  conflict.value = false
  errorMessage.value = ''
  const normalized = normalizeMembers(members.value)
  const payload = {
    stimulus_id: selectedMaterial.value.id,
    status: status.value,
    visibility: visibility.value,
    source: source.value.trim() || null,
    items: normalized.map(({ question_id, position }) => ({ question_id, position })),
  }
  try {
    if (isEdit.value && props.groupId && revision.value) {
      await updateQuestionGroup(editorSubjectId.value, props.groupId, { ...payload, expected_revision: revision.value })
    } else {
      await createQuestionGroup(editorSubjectId.value, payload)
    }
    toast.success(isEdit.value ? '题组已保存' : '题组已创建')
    dirty.value = false
    await router.push('/question-groups')
  } catch (error) {
    if (isRevisionConflict(error)) conflict.value = true
    else errorMessage.value = getApiErrorDetail(error, '保存题组失败')
  } finally { saving.value = false }
}
</script>

<template>
  <div class="flex flex-1 flex-col">
    <header class="flex min-h-14 items-center justify-between gap-3 border-b px-4">
      <div class="flex items-center gap-2"><Button variant="ghost" size="icon" title="返回题组列表" aria-label="返回题组列表" @click="router.push('/question-groups')"><ArrowLeft class="size-4" /></Button><h1 class="text-base font-semibold">{{ isEdit ? '编辑题组' : '创建题组' }}</h1></div>
      <Button :disabled="saving || loading || !canEdit || subjectMismatch || incompatible" @click="submit"><Loader2 v-if="saving" class="mr-2 size-4 animate-spin" /><Save v-else class="mr-2 size-4" />保存</Button>
    </header>

    <main class="flex flex-1 flex-col gap-5 px-4 py-6">
      <Alert v-if="!currentSubjectId || !canEdit" variant="destructive"><AlertTriangle class="size-4" /><AlertTitle>无法编辑</AlertTitle><AlertDescription>{{ !currentSubjectId ? '请先选择学科。' : '你没有编辑该学科题组的权限。' }}</AlertDescription></Alert>
      <Alert v-if="subjectMismatch"><AlertTriangle class="size-4" /><AlertTitle>当前学科已切换</AlertTitle><AlertDescription class="space-y-3"><p>本地草稿仍属于学科 #{{ editorSubjectId }}，题目材料和题目顺序未被重新加载或覆盖。请切回原学科后继续保存，或返回列表放弃草稿。</p><div class="flex flex-wrap gap-2"><Button size="sm" variant="outline" @click="restoreSubject">切回原学科</Button><Button size="sm" variant="ghost" @click="router.push('/question-groups')">返回题组列表</Button></div></AlertDescription></Alert>
      <Alert v-if="incompatible" variant="destructive"><AlertTriangle class="size-4" /><AlertTitle>公开题组包含私有资源</AlertTitle><AlertDescription>{{ compatibilityMessage }}</AlertDescription></Alert>
      <Alert v-if="conflict" variant="destructive"><AlertTriangle class="size-4" /><AlertTitle>题组已被其他人修改</AlertTitle><AlertDescription class="space-y-3"><p>本地题目材料选择和题目顺序均已保留。可以加载服务器最新版本，或继续编辑本地草稿。</p><div class="flex flex-wrap gap-2"><Button size="sm" variant="destructive" @click="load(true)">加载最新并放弃本地</Button><Button size="sm" variant="outline" @click="conflict = false">继续编辑本地</Button></div></AlertDescription></Alert>
      <Alert v-if="errorMessage" variant="destructive"><AlertTriangle class="size-4" /><AlertTitle>操作失败</AlertTitle><AlertDescription>{{ errorMessage }}</AlertDescription></Alert>
      <div v-if="loading" class="flex justify-center py-20"><Loader2 class="size-7 animate-spin text-muted-foreground" /></div>
      <template v-else>
        <div class="grid gap-4 bg-muted/40 p-4 sm:grid-cols-3">
          <div class="space-y-2"><Label>状态</Label><Select v-model="status"><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="draft">草稿</SelectItem><SelectItem value="pending">待审核</SelectItem><SelectItem value="published">已发布</SelectItem><SelectItem value="archived">已归档</SelectItem></SelectContent></Select></div>
          <div class="space-y-2"><Label>可见性</Label><Select v-model="visibility"><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="public">公开</SelectItem><SelectItem value="private">私有</SelectItem></SelectContent></Select></div>
          <div class="space-y-2"><Label for="group-source">来源</Label><Input id="group-source" v-model="source" placeholder="可选" /></div>
        </div>

        <Tabs default-value="material" class="md:hidden"><TabsList class="grid w-full grid-cols-2"><TabsTrigger value="material">题目材料</TabsTrigger><TabsTrigger value="questions">题目 ({{ members.length }})</TabsTrigger></TabsList>
          <TabsContent value="material" class="mt-4 space-y-3"><div class="flex items-center justify-between"><h2 class="text-sm font-semibold">关联题目材料</h2><Button variant="outline" size="sm" @click="materialPickerOpen = true"><Search class="mr-2 size-4" />选择题目材料</Button></div><div v-if="selectedMaterial" class="border p-4"><div class="mb-3 flex items-center justify-between"><Badge variant="outline">#{{ selectedMaterial.id }}</Badge><Button as-child variant="ghost" size="icon" title="编辑题目材料" aria-label="编辑题目材料"><NuxtLink :to="`/materials/${selectedMaterial.id}/edit`"><FilePenLine class="size-4" /></NuxtLink></Button></div><RichContent :content="selectedMaterial.content" /></div><p v-else class="border border-dashed py-12 text-center text-sm text-muted-foreground">尚未选择题目材料</p></TabsContent>
          <TabsContent value="questions" class="mt-4"><div class="mb-3 flex flex-wrap items-center justify-between gap-2"><h2 class="text-sm font-semibold">题目成员</h2><div class="flex gap-2"><Button variant="outline" size="sm" @click="questionCreateOpen = true"><Plus class="mr-2 size-4" />新建</Button><Button size="sm" @click="questionPickerOpen = true"><Plus class="mr-2 size-4" />添加</Button></div></div>
            <draggable v-model="members" item-key="question_id" handle=".drag-handle" class="divide-y border-y" @end="normalizeAfterDrag"><template #item="{ element: member, index }"><article class="flex items-start gap-2 py-3"><button type="button" class="drag-handle mt-1 cursor-grab text-muted-foreground" title="拖动排序" aria-label="拖动排序"><GripVertical class="size-4" /></button><span class="mt-1 w-5 text-center text-xs text-muted-foreground">{{ index + 1 }}</span><div class="min-w-0 flex-1"><div class="mb-1 flex flex-wrap gap-1"><Badge variant="secondary">{{ questionTypeLabel(member.question.q_type) }}</Badge><Badge variant="outline">{{ member.question.status }}</Badge></div><RichContent :content="member.question.content" class="line-clamp-3 text-sm" /></div><div class="flex shrink-0 flex-col"><Button variant="ghost" size="icon" :disabled="index === 0" title="上移" aria-label="上移" @click="moveQuestion(index, index - 1)"><ArrowUp class="size-4" /></Button><Button variant="ghost" size="icon" :disabled="index === members.length - 1" title="下移" aria-label="下移" @click="moveQuestion(index, index + 1)"><ArrowDown class="size-4" /></Button><Button variant="ghost" size="icon" title="从题组移除" aria-label="从题组移除" @click="removeQuestion(member.question_id)"><Trash2 class="size-4" /></Button></div></article></template></draggable><p v-if="members.length === 0" class="border border-dashed py-12 text-center text-sm text-muted-foreground">至少添加一道题</p>
          </TabsContent>
        </Tabs>

        <div class="hidden gap-8 md:grid xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
          <section class="min-w-0 space-y-3"><div class="flex items-center justify-between"><h2 class="text-sm font-semibold">关联题目材料</h2><Button variant="outline" size="sm" @click="materialPickerOpen = true"><Search class="mr-2 size-4" />选择题目材料</Button></div><div v-if="selectedMaterial" class="border p-4"><div class="mb-3 flex items-center justify-between"><div class="flex gap-2"><Badge variant="outline">#{{ selectedMaterial.id }}</Badge><Badge variant="secondary">{{ selectedMaterial.status }}</Badge></div><Button as-child variant="ghost" size="icon" title="编辑题目材料" aria-label="编辑题目材料"><NuxtLink :to="`/materials/${selectedMaterial.id}/edit`"><FilePenLine class="size-4" /></NuxtLink></Button></div><RichContent :content="selectedMaterial.content" /></div><p v-else class="border border-dashed py-16 text-center text-sm text-muted-foreground">尚未选择题目材料</p></section>
          <section class="min-w-0"><div class="mb-3 flex flex-wrap items-center justify-between gap-2"><h2 class="text-sm font-semibold">题目成员 ({{ members.length }})</h2><div class="flex gap-2"><Button variant="outline" size="sm" @click="questionCreateOpen = true"><Plus class="mr-2 size-4" />新建题目</Button><Button size="sm" @click="questionPickerOpen = true"><Plus class="mr-2 size-4" />添加题目</Button></div></div>
            <draggable v-model="members" item-key="question_id" handle=".drag-handle" class="divide-y border-y" @end="normalizeAfterDrag"><template #item="{ element: member, index }"><article class="flex items-start gap-2 py-3"><button type="button" class="drag-handle mt-1 cursor-grab text-muted-foreground" title="拖动排序" aria-label="拖动排序"><GripVertical class="size-4" /></button><span class="mt-1 w-6 text-center text-xs text-muted-foreground">{{ index + 1 }}</span><div class="min-w-0 flex-1"><div class="mb-1 flex gap-2"><Badge variant="secondary">{{ questionTypeLabel(member.question.q_type) }}</Badge><Badge variant="outline">{{ member.question.status }}</Badge></div><RichContent :content="member.question.content" class="line-clamp-3 text-sm" /></div><div class="flex shrink-0"><Button variant="ghost" size="icon" :disabled="index === 0" title="上移" aria-label="上移" @click="moveQuestion(index, index - 1)"><ArrowUp class="size-4" /></Button><Button variant="ghost" size="icon" :disabled="index === members.length - 1" title="下移" aria-label="下移" @click="moveQuestion(index, index + 1)"><ArrowDown class="size-4" /></Button><Button variant="ghost" size="icon" title="从题组移除" aria-label="从题组移除" @click="removeQuestion(member.question_id)"><Trash2 class="size-4" /></Button></div></article></template></draggable>
            <p v-if="members.length === 0" class="border border-dashed py-16 text-center text-sm text-muted-foreground">至少添加一道题</p>
          </section>
        </div>
      </template>
    </main>
  </div>

  <MaterialPickerDialog v-model:open="materialPickerOpen" :subject-id="editorSubjectId" :selected-id="selectedMaterial?.id" :group-visibility="visibility" @select="selectMaterial" />
  <QuestionPickerDialog v-model:open="questionPickerOpen" :subject-id="editorSubjectId" :selected-ids="selectedIds" :group-visibility="visibility" @select="addQuestions" />
  <QuestionEditDialog v-model:open="questionCreateOpen" mode="create" :auto-fill-subject-id="editorSubjectId" @success="addCreatedQuestion" />
</template>