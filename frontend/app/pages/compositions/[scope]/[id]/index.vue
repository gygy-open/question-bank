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
import CompositionCanvas from '~/components/manager/composition/CompositionCanvas.vue'
import CompositionVersionsSheet from '~/components/manager/composition/CompositionVersionsSheet.vue'
import { useCompositions, CompositionConflictError } from '~/composables/useCompositions'
import { normalizeScope } from '~/lib/compositions'
import {
  blocksToReplaceRequest, collectBlockIssues, editorBlocksFromDetail,
  reconcileAfterSave, snapshotBlocks,
} from '~/lib/compositionCanvas'
import type { EditorBlock } from '~/lib/compositionCanvas'
import type { CompositionDetail, CompositionScope } from '~/types'

const route = useRoute()
const router = useRouter()
const api = useCompositions()
const { currentSubjectId, currentSubject } = useSubjectContext()

const scope = computed<CompositionScope>(() => normalizeScope(route.params.scope))
const compositionId = computed(() => Number(route.params.id))

const composition = ref<CompositionDetail | null>(null)
const loading = ref(true)
const savingMeta = ref(false)
const savingBlocks = ref(false)
const title = ref('')
const description = ref('')

const blocks = ref<EditorBlock[]>([])
const savedSnapshot = ref('')
const blockConflict = ref(false)

const saving = computed(() => savingMeta.value || savingBlocks.value)

const metaDirty = computed(
  () =>
    !!composition.value &&
    (title.value.trim() !== (composition.value.title ?? '') ||
      (description.value.trim() || '') !== (composition.value.description ?? '')),
)
const blocksDirty = computed(() => snapshotBlocks(blocks.value) !== savedSnapshot.value)
const dirty = computed(() => metaDirty.value || blocksDirty.value)

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
    blocks.value = editorBlocksFromDetail(data.blocks ?? [])
    savedSnapshot.value = snapshotBlocks(blocks.value)
    blockConflict.value = false
  } catch {
    toast.error('加载组稿失败')
    router.push(`/compositions/${scope.value}`)
  } finally {
    loading.value = false
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
      blockConflict.value = true
      toast.error('组稿已被他人更新，你的本地修改尚未保存')
    } else {
      toast.error('保存失败')
    }
  } finally {
    savingMeta.value = false
  }
}

async function saveBlocks() {
  if (!currentSubjectId.value || !composition.value || saving.value) return
  const issues = collectBlockIssues(blocks.value)
  if (issues.length) {
    toast.error(`存在无法保存的块：${issues[0]}`)
    return
  }
  savingBlocks.value = true
  try {
    const batchId = globalThis.crypto?.randomUUID?.()
    const payload = blocksToReplaceRequest(blocks.value, composition.value.revision, batchId)
    const resp = await api.replaceBlocks(
      currentSubjectId.value,
      scope.value,
      composition.value.id,
      payload,
    )
    blocks.value = reconcileAfterSave(blocks.value, resp)
    composition.value = { ...composition.value, revision: resp.revision }
    savedSnapshot.value = snapshotBlocks(blocks.value)
    blockConflict.value = false
    toast.success('已保存内容')
  } catch (err) {
    if (err instanceof CompositionConflictError && err.kind === 'revision') {
      // 不静默覆盖本地改动：显示冲突条，由用户决定是否放弃本地重新加载。
      blockConflict.value = true
      toast.error('内容已被他人更新，你的本地修改尚未保存')
    } else {
      toast.error('保存内容失败')
    }
  } finally {
    savingBlocks.value = false
  }
}

function reloadFromServer() {
  load()
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

    <div v-else-if="composition" class="mx-auto flex w-full max-w-4xl flex-col gap-6">
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
        v-if="blockConflict"
        class="flex items-center gap-3 rounded-md border border-amber-400 bg-amber-50 px-4 py-3 text-sm dark:border-amber-700 dark:bg-amber-900/20"
      >
        <AlertTriangle class="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
        <span class="flex-1">组稿已被他人更新。你的本地修改仍保留；请重新加载最新版本后再编辑，或先在别处备份当前内容。</span>
        <Button size="sm" variant="outline" @click="reloadFromServer">
          <RefreshCw class="mr-2 h-4 w-4" /> 重新加载（放弃本地）
        </Button>
      </div>

      <!-- 画布 -->
      <div class="flex items-center justify-between">
        <h2 class="text-sm font-medium text-muted-foreground">内容画布</h2>
        <Button size="sm" :disabled="saving || !blocksDirty" @click="saveBlocks">
          <Loader2 v-if="savingBlocks" class="mr-2 h-4 w-4 animate-spin" />
          <Save v-else class="mr-2 h-4 w-4" />
          保存内容
        </Button>
      </div>

      <CompositionCanvas v-model:blocks="blocks" :subject-id="currentSubjectId" />

      <p class="text-xs text-muted-foreground">
        科目：{{ currentSubject?.name || '—' }} · 修订版本 r{{ composition.revision }}
      </p>
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
