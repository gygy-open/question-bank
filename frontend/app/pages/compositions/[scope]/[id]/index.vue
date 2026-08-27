<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Separator } from '@/components/ui/separator'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import {
  ArrowLeft, Loader2, Save, Users, Lock, AlertTriangle, RefreshCw, History, CheckCircle2,
} from '@lucide/vue'
import { toast } from 'vue-sonner'
import CompositionCanvas from '~/components/composition/CompositionCanvas.vue'
import CompositionNumberingPanel from '~/components/composition/CompositionNumberingPanel.vue'
import CompositionQuestionDisplayPanel from '~/components/composition/CompositionQuestionDisplayPanel.vue'
import CompositionVersionsSheet from '~/components/composition/CompositionVersionsSheet.vue'
import { useCompositions, CompositionConflictError } from '~/composables/useCompositions'
import { normalizeScope } from '~/lib/compositions'
import {
  applyQuestionNumbers, collectDocumentIssues, collectStaleQuestionNodeIds, documentFromNodes,
  documentToReplaceRequest, hasAnyQuestionNumber, snapshotDocument,
} from '~/lib/compositionDocument'
import type { EditorDocument, NumberingMode } from '~/lib/compositionDocument'
import type { AnswerFieldKey, CompositionDetail, CompositionScope, QuestionRevisionStatus } from '~/types'

const route = useRoute()
const router = useRouter()
const api = useCompositions()
const { currentSubjectId, currentSubject } = useSubjectContext()

const scope = computed<CompositionScope>(() => normalizeScope(route.params.scope))
const compositionId = computed(() => Number(route.params.id))

const composition = ref<CompositionDetail | null>(null)
const loading = ref(true)
const savingMeta = ref(false)
const savingNodes = ref(false)
const title = ref('')
const description = ref('')

const document = ref<EditorDocument>({ nodes: [] })
const savedSnapshot = ref('')
const editConflict = ref(false)

// 题目版本状态（question_id → 实时 revision/可用性），只用于 stale/deleted 标记，不渲染内容。
const questionStatus = ref<Map<number, QuestionRevisionStatus>>(new Map())
const syncingNodes = ref(false)

const saving = computed(() => savingMeta.value || savingNodes.value)

const metaDirty = computed(
  () =>
    !!composition.value &&
    (title.value.trim() !== (composition.value.title ?? '') ||
      (description.value.trim() || '') !== (composition.value.description ?? '')),
)
const nodesDirty = computed(() => snapshotDocument(document.value) !== savedSnapshot.value)
const dirty = computed(() => metaDirty.value || nodesDirty.value)
// 存在过期题目（题库有更新但稿件仍是定格旧内容）。定稿不被阻止，仅提示。
const hasStaleQuestions = computed(
  () => collectStaleQuestionNodeIds(document.value, questionStatus.value).length > 0,
)
const numberingEnabled = computed(() => composition.value?.numbering_enabled ?? false)
const questionDisplay = computed<Record<AnswerFieldKey, boolean>>(
  () => composition.value?.question_display ?? { answer: false, thinking: false, analysis: false, summary: false },
)

async function load() {
  if (!currentSubjectId.value) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    const data = await api.getComposition(currentSubjectId.value, scope.value, compositionId.value)
    composition.value = data
    title.value = data.title
    description.value = data.description ?? ''
    document.value = documentFromNodes(data.nodes ?? [])
    savedSnapshot.value = snapshotDocument(document.value)
    editConflict.value = false
    await loadQuestionStatus()
  } catch {
    toast.error('加载组稿失败')
    router.push(`/compositions/${scope.value}`)
  } finally {
    loading.value = false
  }
}

// 拉取题目版本状态（stale/deleted 标记）；失败静默降级为无状态。
async function loadQuestionStatus() {
  if (!currentSubjectId.value || !composition.value) return
  try {
    const list = await api.getQuestionRevisions(
      currentSubjectId.value,
      scope.value,
      composition.value.id,
    )
    questionStatus.value = new Map(list.map((s) => [s.question_id, s]))
  } catch {
    // 状态获取失败时保持空 Map（不显示过期/删除标记，不影响冻结快照渲染）。
  }
}

onMounted(load)
watch([currentSubjectId, scope, compositionId], load)

async function saveMeta() {
  if (!currentSubjectId.value || !composition.value || saving.value) return
  if (!title.value.trim()) {
    toast.error('请输入标题')
    return
  }
  savingMeta.value = true
  try {
    const updated = await api.updateComposition(
      currentSubjectId.value,
      scope.value,
      composition.value.id,
      {
        expected_revision: composition.value.revision,
        title: title.value.trim(),
        description: description.value.trim() || null,
      },
    )
    // 合并元数据并同步共享 revision，供后续 block 保存使用。
    composition.value = { ...composition.value, ...updated }
    title.value = updated.title
    description.value = updated.description ?? ''
    toast.success('已保存标题/描述')
  } catch (err) {
    if (err instanceof CompositionConflictError && err.kind === 'revision') {
      // 与内容保存冲突采用同一策略：保留全部本地修改，由用户决定何时放弃并重载。
      editConflict.value = true
      toast.error('组稿已被他人更新，你的本地修改尚未保存')
    } else {
      toast.error('保存失败')
    }
  } finally {
    savingMeta.value = false
  }
}

async function saveNodes() {
  if (!currentSubjectId.value || !composition.value || saving.value) return
  const issues = collectDocumentIssues(document.value)
  if (issues.length) {
    toast.error(`存在无法保存的块：${issues[0]}`)
    return
  }
  savingNodes.value = true
  try {
    const batchId = globalThis.crypto?.randomUUID?.()
    const payload = documentToReplaceRequest(document.value, composition.value.revision, batchId)
    const resp = await api.replaceNodes(
      currentSubjectId.value,
      scope.value,
      composition.value.id,
      payload,
    )
    document.value = documentFromNodes(resp.nodes)
    composition.value = { ...composition.value, revision: resp.revision }
    savedSnapshot.value = snapshotDocument(document.value)
    editConflict.value = false
    toast.success('已保存内容')
    await loadQuestionStatus()
  } catch (err) {
    if (err instanceof CompositionConflictError && err.kind === 'revision') {
      // 不静默覆盖本地改动：显示冲突条，由用户决定是否放弃本地重新加载。
      editConflict.value = true
      toast.error('内容已被他人更新，你的本地修改尚未保存')
    } else {
      toast.error('保存内容失败')
    }
  } finally {
    savingNodes.value = false
  }
}

// 同步 question 节点：刷新冻结快照并立即落库。dirty 时禁止（画布已把按钮禁用）。
async function syncNodes(nodeIds: string[]) {
  if (!currentSubjectId.value || !composition.value || syncingNodes.value) return
  if (dirty.value || !nodeIds.length) return
  syncingNodes.value = true
  try {
    const resp = await api.syncQuestionNodes(
      currentSubjectId.value,
      scope.value,
      composition.value.id,
      { expected_revision: composition.value.revision, node_ids: nodeIds },
    )
    document.value = documentFromNodes(resp.nodes)
    composition.value = { ...composition.value, revision: resp.revision }
    savedSnapshot.value = snapshotDocument(document.value)
    toast.success(`已同步 ${nodeIds.length} 道题目`)
    await loadQuestionStatus()
  } catch (err) {
    if (err instanceof CompositionConflictError && err.kind === 'revision') {
      editConflict.value = true
      toast.error('组稿已被他人更新，同步失败；你的本地修改仍保留')
    } else {
      toast.error('同步题目失败')
    }
  } finally {
    syncingNodes.value = false
  }
}

function reloadFromServer() {
  load()
}

// 题号开关：即时持久化（bump revision）；开启且无题号时本地按全局顺序预填，待“保存内容”落库。
async function toggleNumbering(value: boolean) {
  if (!currentSubjectId.value || !composition.value || saving.value) return
  savingMeta.value = true
  try {
    const updated = await api.updateComposition(
      currentSubjectId.value,
      scope.value,
      composition.value.id,
      { expected_revision: composition.value.revision, numbering_enabled: value },
    )
    composition.value = { ...composition.value, ...updated }
    if (value && !hasAnyQuestionNumber(document.value)) {
      document.value = applyQuestionNumbers(document.value, 'global')
    }
  } catch (err) {
    if (err instanceof CompositionConflictError && err.kind === 'revision') {
      editConflict.value = true
      toast.error('组稿已被他人更新，你的本地修改尚未保存')
    } else {
      toast.error('保存失败')
    }
  } finally {
    savingMeta.value = false
  }
}

// 题目显示：全局字段开关即时持久化（bump revision）。
async function toggleDisplayField(key: AnswerFieldKey, value: boolean) {
  if (!currentSubjectId.value || !composition.value || saving.value) return
  savingMeta.value = true
  try {
    const updated = await api.updateComposition(
      currentSubjectId.value,
      scope.value,
      composition.value.id,
      {
        expected_revision: composition.value.revision,
        question_display: { ...questionDisplay.value, [key]: value },
      },
    )
    composition.value = { ...composition.value, ...updated }
  } catch (err) {
    if (err instanceof CompositionConflictError && err.kind === 'revision') {
      editConflict.value = true
      toast.error('组稿已被他人更新，你的本地修改尚未保存')
    } else {
      toast.error('保存失败')
    }
  } finally {
    savingMeta.value = false
  }
}

// 自动填充题号（一次性，覆盖已有）：仅改本地文档，经“保存内容”落库。
function autofillNumbers(mode: NumberingMode) {
  if (!composition.value) return
  if (
    hasAnyQuestionNumber(document.value) &&
    !window.confirm('自动填充将覆盖所有已有题号，确定继续？')
  ) {
    return
  }
  document.value = applyQuestionNumbers(document.value, mode)
}

// --- 定稿（冻结当前 revision 为不可变版本） ---
const finalizeOpen = ref(false)
const finalizeLabel = ref('')
const finalizing = ref(false)
const versionsOpen = ref(false)
const versionsSheet = ref<InstanceType<typeof CompositionVersionsSheet> | null>(null)

function openFinalize() {
  if (dirty.value) {
    toast.error('有未保存修改，请先保存后再定稿')
    return
  }
  finalizeLabel.value = ''
  finalizeOpen.value = true
}

async function doFinalize() {
  if (!currentSubjectId.value || !composition.value || finalizing.value) return
  finalizing.value = true
  try {
    const version = await api.finalizeVersion(
      currentSubjectId.value,
      scope.value,
      composition.value.id,
      {
        expected_revision: composition.value.revision,
        label: finalizeLabel.value.trim() || null,
      },
    )
    // 定稿不改动本地 revision；仅提示并刷新版本列表。
    finalizeOpen.value = false
    toast.success(`已定稿为版本 v${version.version_no}`)
    versionsOpen.value = true
    versionsSheet.value?.refresh()
  } catch (err) {
    if (err instanceof CompositionConflictError && err.kind === 'revision') {
      // 定稿 revision 冲突：保留本地内容并复用现有冲突条。
      finalizeOpen.value = false
      blockConflict.value = true
      toast.error('组稿已被他人更新，定稿失败；你的本地修改仍保留')
    } else {
      toast.error('定稿失败')
    }
  } finally {
    finalizing.value = false
  }
}

function back() {
  router.push(`/compositions/${scope.value}`)
}

// --- 离开前提示未保存修改 ---
function beforeUnloadHandler(e: BeforeUnloadEvent) {
  if (dirty.value) {
    e.preventDefault()
    e.returnValue = ''
  }
}
onMounted(() => window.addEventListener('beforeunload', beforeUnloadHandler))
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnloadHandler))

onBeforeRouteLeave(() => {
  if (dirty.value && !window.confirm('有未保存的修改，确定要离开吗？')) {
    return false
  }
  return true
})
</script>

<template>
  <header class="flex h-16 shrink-0 items-center gap-2 border-b px-4">
    <Button variant="ghost" size="icon" class="h-8 w-8" @click="back">
      <ArrowLeft class="h-4 w-4" />
    </Button>
    <div class="min-w-0 flex-1">
      <p class="truncate text-sm font-medium">{{ composition?.title || '组稿' }}</p>
    </div>
    <Badge v-if="dirty" variant="outline" class="gap-1 text-amber-600 dark:text-amber-400">
      未保存
    </Badge>
    <Badge variant="outline" class="gap-1">
      <component :is="scope === 'shared' ? Users : Lock" class="h-3 w-3" />
      {{ scope === 'shared' ? '共享' : '个人' }}
    </Badge>
    <TooltipProvider :delay-duration="300">
      <Tooltip>
        <TooltipTrigger as-child>
          <Button variant="ghost" size="icon" class="h-8 w-8" :disabled="!composition" @click="versionsOpen = true">
            <History class="h-4 w-4" />
          </Button>
        </TooltipTrigger>
        <TooltipContent>版本历史</TooltipContent>
      </Tooltip>
    </TooltipProvider>
    <TooltipProvider :delay-duration="300">
      <Tooltip>
        <TooltipTrigger as-child>
          <!-- span 包裹：disabled 按钮不触发 tooltip 时仍可悬停提示 -->
          <span>
            <Button size="sm" variant="outline" :disabled="!composition || saving || dirty" @click="openFinalize">
              <CheckCircle2 class="mr-2 h-4 w-4" /> 定稿
            </Button>
          </span>
        </TooltipTrigger>
        <TooltipContent>{{ dirty ? '请先保存后再定稿' : '冻结当前内容为不可变版本' }}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  </header>

  <div class="flex flex-1 flex-col px-4 py-6">
    <div v-if="loading" class="flex justify-center py-16">
      <Loader2 class="h-6 w-6 animate-spin text-muted-foreground" />
    </div>

    <div v-else-if="composition" class="mx-auto flex w-full max-w-6xl flex-col gap-6">
      <!-- 元数据 -->
      <div class="flex flex-col gap-4 sm:flex-row sm:items-end">
        <div class="flex-1 space-y-2">
          <Label>标题</Label>
          <Input v-model="title" placeholder="组稿标题" />
        </div>
        <Button size="sm" variant="outline" :disabled="saving || !metaDirty" @click="saveMeta">
          <Loader2 v-if="savingMeta" class="mr-2 h-4 w-4 animate-spin" />
          <Save v-else class="mr-2 h-4 w-4" />
          保存标题/描述
        </Button>
      </div>
      <div class="space-y-2">
        <Label>描述</Label>
        <Textarea v-model="description" placeholder="组稿说明（可选）" rows="2" />
      </div>

      <Separator />

      <!-- 冲突条 -->
      <div
        v-if="editConflict"
        class="flex items-center gap-3 rounded-md border border-amber-400 bg-amber-50 px-4 py-3 text-sm dark:border-amber-700 dark:bg-amber-900/20"
      >
        <AlertTriangle class="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
        <span class="flex-1">组稿已被他人更新。你的本地修改仍保留；请重新加载最新版本后再编辑，或先在别处备份当前内容。</span>
        <Button size="sm" variant="outline" @click="reloadFromServer">
          <RefreshCw class="mr-2 h-4 w-4" /> 重新加载（放弃本地）
        </Button>
      </div>

      <!-- 画布 + 题号面板 -->
      <div class="flex flex-col gap-6 lg:flex-row lg:items-start">
        <div class="flex min-w-0 flex-1 flex-col gap-6">
          <div class="flex items-center justify-between">
            <h2 class="text-sm font-medium text-muted-foreground">内容画布</h2>
            <Button size="sm" :disabled="saving || !nodesDirty" @click="saveNodes">
              <Loader2 v-if="savingNodes" class="mr-2 h-4 w-4 animate-spin" />
              <Save v-else class="mr-2 h-4 w-4" />
              保存内容
            </Button>
          </div>

          <CompositionCanvas
            v-model:document="document"
            :subject-id="currentSubjectId"
            :question-status="questionStatus"
            :sync-disabled="dirty"
            :syncing="syncingNodes"
            :numbering-enabled="numberingEnabled"
            :global-display-fields="questionDisplay"
            @sync="syncNodes"
          />

          <p class="text-xs text-muted-foreground">
            科目：{{ currentSubject?.name || '—' }} · 修订版本 r{{ composition.revision }}
          </p>
        </div>

        <aside class="flex flex-col gap-4 lg:sticky lg:top-6 lg:w-72 lg:shrink-0">
          <CompositionNumberingPanel
            :enabled="numberingEnabled"
            :disabled="saving"
            @update:enabled="toggleNumbering"
            @autofill="autofillNumbers"
          />
          <CompositionQuestionDisplayPanel
            :fields="questionDisplay"
            :disabled="saving"
            @toggle="toggleDisplayField"
          />
        </aside>
      </div>
    </div>
  </div>

  <!-- 定稿对话框 -->
  <Dialog v-model:open="finalizeOpen">
    <DialogContent>
      <DialogHeader>
        <DialogTitle>定稿为新版本</DialogTitle>
        <DialogDescription>
          将冻结当前修订版本
          <span class="font-mono font-medium">r{{ composition?.revision }}</span>
          为不可变版本。定稿不会修改组稿本身，可继续编辑。
        </DialogDescription>
      </DialogHeader>
      <div class="space-y-2">
        <Label>版本备注（可选）</Label>
        <Input v-model="finalizeLabel" placeholder="例如：期中卷终稿" maxlength="200" />
      </div>
      <div
        v-if="hasStaleQuestions"
        class="flex items-start gap-2 rounded-md border border-amber-400 bg-amber-50 px-3 py-2 text-xs dark:border-amber-700 dark:bg-amber-900/20"
      >
        <AlertTriangle class="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600 dark:text-amber-400" />
        <span>部分题目在题库中已更新，本次将冻结当前显示的旧版本内容。如需最新内容，请先取消并“同步全部”。</span>
      </div>
      <DialogFooter>
        <Button variant="outline" :disabled="finalizing" @click="finalizeOpen = false">取消</Button>
        <Button :disabled="finalizing" @click="doFinalize">
          <Loader2 v-if="finalizing" class="mr-2 h-4 w-4 animate-spin" />
          <CheckCircle2 v-else class="mr-2 h-4 w-4" />
          确认定稿
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>

  <!-- 版本列表侧栏 -->
  <CompositionVersionsSheet
    v-if="composition && currentSubjectId"
    ref="versionsSheet"
    v-model:open="versionsOpen"
    :subject-id="currentSubjectId"
    :scope="scope"
    :composition-id="composition.id"
  />
</template>
