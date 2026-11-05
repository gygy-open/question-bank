<script setup lang="ts">
/**
 * 元素归纳的「待归纳」面板(类型管理页的一个标签页)。
 *
 * - 顶部:未归类条数、最近一次归纳任务的状态、「开始归纳 / 重新归纳」按钮(学科管理权限);
 * - 每个候选一张卡片:名称、定义、条数、示例、AI 建议的上级与相似类型;
 * - 操作(类型维护权限):新建为类型(可改名、换上级)、并入已有类型、忽略。
 *
 * 归纳任务进行中时每 3 秒刷新一次;处理完任一候选后通知外层刷新类型树(引用数会变)。
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import { Loader2, Sparkles } from '@lucide/vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'
import MathText from '@/components/structure/MathText.vue'
import StructTypeSelect from '@/components/structure/StructTypeSelect.vue'
import { getApiErrorDetail } from '@/lib/apiErrors'
import { formatDateTime } from '@/lib/locale'
import type { StructCandidatesView, StructType, StructTypeCandidate } from '~/types'

const props = defineProps<{
  subjectId: number | null
  types: StructType[]
  /** 能否确认候选(类型维护权限)。 */
  editable: boolean
  /** 能否发起归纳(学科管理权限)。 */
  canInduce: boolean
}>()

const emit = defineEmits<{
  (e: 'changed'): void
  (e: 'count', value: number): void
}>()

const { t } = useI18n()
const api = useStructure()

const view = ref<StructCandidatesView | null>(null)
const loading = ref(false)
const inducing = ref(false)
const busyId = ref<number | null>(null)
let timer: ReturnType<typeof setTimeout> | null = null

// 新建 / 并入对话框
const dialogOpen = ref(false)
const dialogMode = ref<'accept' | 'merge'>('accept')
const dialogCandidate = ref<StructTypeCandidate | null>(null)
const formName = ref('')
const formDefinition = ref('')
const formTypeId = ref<number | null>(null)

const running = computed(() => !!view.value?.job && ['pending', 'running'].includes(view.value.job.status))
const totalUnclassified = computed(() => (view.value?.unclassified.condition ?? 0) + (view.value?.unclassified.ask ?? 0))
const enoughData = computed(() => {
  const v = view.value
  return !!v && Math.max(v.unclassified.condition, v.unclassified.ask) >= v.min_items
})
const groups = computed(() => {
  const items = view.value?.items ?? []
  return [
    { kind: 'condition' as const, title: t('structure.conditions'), items: items.filter(c => c.kind === 'condition') },
    { kind: 'ask' as const, title: t('structure.asks'), items: items.filter(c => c.kind === 'ask') },
  ].filter(g => g.items.length)
})
const jobText = computed(() => {
  const job = view.value?.job
  if (!job) return ''
  if (job.status === 'failed' && job.error) return t('structure.induce.jobFailed', { error: job.error })
  if (job.status === 'paused') return t('structure.induce.jobPaused', { reason: t(`structure.pausedReasons.${job.paused_reason ?? 'unavailable'}`) })
  if (job.status === 'succeeded' && job.finished_at) return t('structure.induce.jobDone', { time: formatDateTime(job.finished_at) })
  return t(`structure.induce.jobStatuses.${job.status}`)
})

// region 公共操作

async function load(): Promise<void> {
  if (props.subjectId == null) return
  loading.value = true
  try {
    view.value = await api.listCandidates(props.subjectId)
    emit('count', view.value.items.length)
  } catch (e) {
    toast.error(t('structure.types.loadFailed'), { description: getApiErrorDetail(e, '') })
  } finally {
    loading.value = false
    schedulePoll()
  }
}

async function startInduce(): Promise<void> {
  if (props.subjectId == null) return
  inducing.value = true
  try {
    await api.induce(props.subjectId)
    toast.success(t('structure.induce.queued'))
    await load()
  } catch (e) {
    toast.error(t('structure.types.actionFailed'), { description: getApiErrorDetail(e, '') })
  } finally {
    inducing.value = false
  }
}

function openAccept(candidate: StructTypeCandidate): void {
  dialogMode.value = 'accept'
  dialogCandidate.value = candidate
  formName.value = candidate.name
  formDefinition.value = candidate.definition ?? ''
  formTypeId.value = candidate.suggested_parent_id
  dialogOpen.value = true
}

function openMerge(candidate: StructTypeCandidate): void {
  dialogMode.value = 'merge'
  dialogCandidate.value = candidate
  formTypeId.value = candidate.similar_type_id
  dialogOpen.value = true
}

async function submitDialog(): Promise<void> {
  const candidate = dialogCandidate.value
  if (!candidate) return
  if (dialogMode.value === 'merge' && formTypeId.value == null) return
  await act(candidate, async () => {
    if (dialogMode.value === 'accept') {
      await api.acceptCandidate(candidate.id, {
        name: formName.value.trim() || undefined,
        parent_id: formTypeId.value,
        definition: formDefinition.value.trim() || null,
      })
      toast.success(t('structure.induce.accepted', { count: candidate.count }))
    } else {
      await api.mergeCandidate(candidate.id, formTypeId.value as number)
      toast.success(t('structure.induce.merged', { count: candidate.count }))
    }
    dialogOpen.value = false
  })
}

async function ignore(candidate: StructTypeCandidate): Promise<void> {
  await act(candidate, async () => {
    await api.ignoreCandidate(candidate.id)
  })
}

// endregion

// region 内部辅助函数

async function act(candidate: StructTypeCandidate, action: () => Promise<void>): Promise<void> {
  busyId.value = candidate.id
  try {
    await action()
    emit('changed')
    await load()
  } catch (e) {
    toast.error(t('structure.types.actionFailed'), { description: getApiErrorDetail(e, '') })
  } finally {
    busyId.value = null
  }
}

function schedulePoll(): void {
  if (timer) clearTimeout(timer)
  timer = null
  if (running.value) timer = setTimeout(() => { void load() }, 3000)
}

// endregion

watch(() => props.subjectId, () => { void load() }, { immediate: true })
onBeforeUnmount(() => { if (timer) clearTimeout(timer) })
defineExpose({ load })
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center gap-3 rounded-lg border bg-card px-4 py-3">
      <div class="min-w-0 flex-1 space-y-0.5">
        <p class="text-sm">
          {{ t('structure.induce.unclassified', {
            conditions: view?.unclassified.condition ?? 0,
            asks: view?.unclassified.ask ?? 0,
          }) }}
        </p>
        <p class="text-xs text-muted-foreground">
          <template v-if="view && !enoughData">{{ t('structure.induce.notEnough', { min: view.min_items }) }}</template>
          <template v-else>{{ t('structure.induce.hint') }}</template>
        </p>
        <p v-if="jobText" class="text-xs text-muted-foreground">{{ jobText }}</p>
      </div>
      <Button
        v-if="canInduce"
        :disabled="inducing || running || !enoughData"
        @click="startInduce"
      >
        <Loader2 v-if="inducing || running" class="mr-2 h-4 w-4 animate-spin" />
        <Sparkles v-else class="mr-2 h-4 w-4" />
        {{ view?.items.length ? t('structure.induce.rerun') : t('structure.induce.run') }}
      </Button>
    </div>

    <div v-if="loading && !view" class="flex items-center gap-2 py-6 text-sm text-muted-foreground">
      <Loader2 class="h-4 w-4 animate-spin" /> {{ t('common.loading') }}
    </div>
    <p v-else-if="!groups.length && (!totalUnclassified || enoughData)" class="py-6 text-center text-sm text-muted-foreground">
      {{ totalUnclassified ? t('structure.induce.emptyWithItems') : t('structure.induce.empty') }}
    </p>

    <section v-for="group in groups" :key="group.kind" class="space-y-2">
      <h3 class="text-sm font-medium">{{ group.title }}</h3>
      <div class="grid gap-3 lg:grid-cols-2">
        <article
          v-for="candidate in group.items"
          :key="candidate.id"
          class="flex flex-col gap-2 rounded-lg border bg-card p-3"
        >
          <div class="flex items-start gap-2">
            <div class="min-w-0 flex-1">
              <p class="font-medium">{{ candidate.name }}</p>
              <p v-if="candidate.definition" class="text-sm text-muted-foreground">{{ candidate.definition }}</p>
            </div>
            <Badge variant="secondary" class="shrink-0 font-normal">{{ t('structure.induce.count', { count: candidate.count }) }}</Badge>
          </div>
          <ul class="space-y-1 text-sm">
            <li v-for="(sample, i) in candidate.samples" :key="i" class="flex gap-1.5">
              <span class="text-muted-foreground">·</span><MathText class="min-w-0" :text="sample" />
            </li>
          </ul>
          <div class="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
            <span v-if="candidate.suggested_parent_path.length">
              {{ t('structure.induce.suggestedParent', { path: candidate.suggested_parent_path.join(' / ') }) }}
            </span>
            <span v-if="candidate.similar_type_path.length" class="text-amber-700 dark:text-amber-300">
              {{ t('structure.induce.similarType', { path: candidate.similar_type_path.join(' / ') }) }}
            </span>
          </div>
          <div v-if="editable" class="mt-auto flex flex-wrap gap-2 pt-1">
            <Button size="sm" :disabled="busyId === candidate.id" @click="openAccept(candidate)">{{ t('structure.induce.accept') }}</Button>
            <Button size="sm" variant="outline" :disabled="busyId === candidate.id" @click="openMerge(candidate)">{{ t('structure.induce.merge') }}</Button>
            <Button size="sm" variant="ghost" :disabled="busyId === candidate.id" @click="ignore(candidate)">{{ t('structure.induce.ignore') }}</Button>
          </div>
        </article>
      </div>
    </section>
  </div>

  <Dialog v-model:open="dialogOpen">
    <DialogContent class="sm:max-w-md">
      <DialogHeader>
        <DialogTitle>
          {{ dialogMode === 'accept'
            ? t('structure.induce.acceptTitle', { name: dialogCandidate?.name ?? '' })
            : t('structure.induce.mergeTitle', { name: dialogCandidate?.name ?? '' }) }}
        </DialogTitle>
        <DialogDescription>
          {{ dialogMode === 'accept' ? t('structure.induce.acceptHint') : t('structure.induce.mergeHint') }}
        </DialogDescription>
      </DialogHeader>
      <div class="space-y-3">
        <template v-if="dialogMode === 'accept'">
          <div class="space-y-1.5">
            <Label>{{ t('structure.types.name') }}</Label>
            <Input v-model="formName" maxlength="128" />
          </div>
          <div class="space-y-1.5">
            <Label>{{ t('structure.induce.parent') }}</Label>
            <StructTypeSelect
              v-model="formTypeId"
              :types="types"
              :kind="dialogCandidate?.kind"
              include-inactive
              :placeholder="t('structure.induce.parentDefault')"
            />
          </div>
          <div class="space-y-1.5">
            <Label>{{ t('structure.types.definition') }}</Label>
            <Textarea v-model="formDefinition" rows="3" :placeholder="t('structure.types.definitionPlaceholder')" />
          </div>
        </template>
        <div v-else class="space-y-1.5">
          <Label>{{ t('structure.types.pickTarget') }}</Label>
          <StructTypeSelect v-model="formTypeId" :types="types" :kind="dialogCandidate?.kind" :allow-none="false" />
        </div>
      </div>
      <DialogFooter>
        <Button variant="outline" @click="dialogOpen = false">{{ t('common.cancel') }}</Button>
        <Button
          :disabled="busyId != null || (dialogMode === 'merge' && formTypeId == null)"
          @click="submitDialog"
        >
          <Loader2 v-if="busyId != null" class="mr-2 h-4 w-4 animate-spin" />
          {{ t('common.confirm') }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
