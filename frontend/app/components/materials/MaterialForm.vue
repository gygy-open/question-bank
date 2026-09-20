<script setup lang="ts">
import { computed, nextTick, onActivated, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { AlertTriangle, ArrowLeft, Loader2, Save } from '@lucide/vue'
import { toast } from 'vue-sonner'
import RichEditor from '@/components/rich-editor/RichEditor.vue'
import { isEmptyRichDoc } from '@/components/rich-editor/richDoc'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { getApiErrorDetail, hasEditorSubjectMismatch, isRevisionConflict } from '@/lib/questionGroupEditor'
import type { QuestionStatus, RichDoc, Stimulus } from '@/types'

const props = defineProps<{ materialId?: number }>()
const router = useRouter()
const { currentSubjectId, setSubject } = useSubjectContext()
const { can } = usePermissions()
const { createMaterial, getMaterial, updateMaterial } = useMaterials()
const editorSubjectId = ref<number | null>(null)
const canEdit = computed(() => can(Capability.EDIT_QUESTION, editorSubjectId.value))
const isEdit = computed(() => props.materialId != null)
const subjectMismatch = computed(() => hasEditorSubjectMismatch(editorSubjectId.value, currentSubjectId.value))

const content = ref<RichDoc>(null)
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

const applyMaterial = (material: Stimulus) => {
  content.value = structuredClone(material.content)
  status.value = material.status
  visibility.value = material.visibility
  source.value = material.source ?? ''
  revision.value = material.revision
  dirty.value = false
  conflict.value = false
  errorMessage.value = ''
}

const load = async (force = false) => {
  if (!isEdit.value || !props.materialId || !editorSubjectId.value || (dirty.value && !force)) return
  loading.value = true
  hydrating.value = true
  try {
    applyMaterial(await getMaterial(editorSubjectId.value, props.materialId))
  } catch (error) {
    errorMessage.value = getApiErrorDetail(error, '题目材料加载失败')
  } finally {
    loading.value = false
    await nextTick()
    dirty.value = false
    hydrating.value = false
  }
}

watch([content, status, visibility, source], () => { if (!hydrating.value) dirty.value = true }, { deep: true })
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

const submit = async () => {
  if (!editorSubjectId.value || subjectMismatch.value || !canEdit.value || isEmptyRichDoc(content.value)) {
    errorMessage.value = !editorSubjectId.value ? '请先选择学科' : subjectMismatch.value ? '请先切回草稿所属学科' : !canEdit.value ? '你没有编辑该学科题目材料的权限' : '请填写题目材料内容'
    return
  }
  saving.value = true
  conflict.value = false
  errorMessage.value = ''
  const payload = { content: content.value, status: status.value, visibility: visibility.value, source: source.value.trim() || null }
  try {
    if (isEdit.value && props.materialId && revision.value) {
      await updateMaterial(editorSubjectId.value, props.materialId, { ...payload, expected_revision: revision.value })
    } else {
      await createMaterial(editorSubjectId.value, payload)
    }
    toast.success(isEdit.value ? '题目材料已保存' : '题目材料已创建')
    dirty.value = false
    await router.push('/materials')
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
      <Button :disabled="saving || loading || !canEdit || subjectMismatch" @click="submit"><Loader2 v-if="saving" class="mr-2 size-4 animate-spin" /><Save v-else class="mr-2 size-4" />保存</Button>
    </header>

    <main class="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-5 px-4 py-6">
      <Alert v-if="!currentSubjectId || !canEdit" variant="destructive"><AlertTriangle class="size-4" /><AlertTitle>无法编辑</AlertTitle><AlertDescription>{{ !currentSubjectId ? '请先选择学科。' : '你没有编辑该学科题目材料的权限。' }}</AlertDescription></Alert>
      <Alert v-if="subjectMismatch"><AlertTriangle class="size-4" /><AlertTitle>当前学科已切换</AlertTitle><AlertDescription class="space-y-3"><p>本地草稿仍属于学科 #{{ editorSubjectId }}，未被重新加载或覆盖。请切回原学科后继续保存，或返回列表放弃草稿。</p><div class="flex flex-wrap gap-2"><Button size="sm" variant="outline" @click="restoreSubject">切回原学科</Button><Button size="sm" variant="ghost" @click="router.push('/materials')">返回题目材料列表</Button></div></AlertDescription></Alert>
      <Alert v-if="conflict" variant="destructive">
        <AlertTriangle class="size-4" /><AlertTitle>题目材料已被其他人修改</AlertTitle>
        <AlertDescription class="space-y-3"><p>你的本地内容仍然保留。可以加载服务器最新版本，或继续编辑本地草稿后再决定。</p><div class="flex flex-wrap gap-2"><Button size="sm" variant="destructive" @click="load(true)">加载最新并放弃本地</Button><Button size="sm" variant="outline" @click="conflict = false">继续编辑本地</Button></div></AlertDescription>
      </Alert>
      <Alert v-if="errorMessage" variant="destructive"><AlertTriangle class="size-4" /><AlertTitle>操作失败</AlertTitle><AlertDescription>{{ errorMessage }}</AlertDescription></Alert>
      <div v-if="loading" class="flex justify-center py-20"><Loader2 class="size-7 animate-spin text-muted-foreground" /></div>
      <template v-else>
        <div class="grid gap-4 bg-muted/40 p-4 sm:grid-cols-3">
          <div class="space-y-2"><Label>状态</Label><Select v-model="status"><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="draft">草稿</SelectItem><SelectItem value="pending">待审核</SelectItem><SelectItem value="published">已发布</SelectItem><SelectItem value="archived">已归档</SelectItem></SelectContent></Select></div>
          <div class="space-y-2"><Label>可见性</Label><Select v-model="visibility"><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="public">公开</SelectItem><SelectItem value="private">私有</SelectItem></SelectContent></Select></div>
          <div class="space-y-2"><Label for="material-source">来源</Label><Input id="material-source" v-model="source" placeholder="可选" /></div>
        </div>
        <div class="space-y-2"><Label>题目材料内容</Label><RichEditor v-model="content" /></div>
      </template>
    </main>
  </div>
</template>