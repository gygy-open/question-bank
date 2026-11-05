<script setup lang="ts">
/**
 * 解答结构面板(规格 §12.3 N7):查看、审核、编辑一道题某种解法的步骤拆解。
 *
 * - 上方列出依据的题干条目(C1… 条件、Q1… 设问),步骤里的引用用同样的编号;
 * - 每一步:目标、方法(类型路径 × 权重,未归类显示 AI 的描述)、用到的条件 / 设问 / 前序步骤、
 *   作答的设问、结论、关键步标记、常见错误;
 * - 思维量 = 各步权重之和;题目的思维量难度取已采纳解法的最小值;
 * - 编辑:逐步改写、选方法、勾选依赖、增删排序,保存为新的人工快照。
 *
 * 审核页通过 defineExpose 暴露 accept / reject / startEdit / redecompose,供快捷键调用。
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import {
  ArrowDown, ArrowUp, Check, Loader2, Pencil, Plus, RefreshCw, Sparkles, Star, Trash2, TriangleAlert, X,
} from '@lucide/vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { Textarea } from '@/components/ui/textarea'
import MathText from '@/components/structure/MathText.vue'
import StructTypeSelect from '@/components/structure/StructTypeSelect.vue'
import { getApiErrorDetail } from '@/lib/apiErrors'
import { formatDateTime, formatNumber } from '@/lib/locale'
import { cn } from '@/lib/utils'
import type { SolutionMisconception, SolutionRun, SolutionView, StructCheckIssue, StructType } from '~/types'

const props = withDefaults(defineProps<{
  questionId: number
  /** 同时有待审与已采纳版本时默认展示哪一个(审核页传 draft)。 */
  preferRun?: 'draft' | 'accepted'
  /** 默认展示第几种解法(审核页传队列项的解法)。 */
  initialSolutionNo?: number
}>(), { preferRun: 'draft', initialSolutionNo: 1 })

const emit = defineEmits<{ (e: 'changed'): void }>()

const { t } = useI18n()
const api = useStructure()

/** 编辑中的一步;uid 只在本地使用,用来在排序时保持「依赖哪一步」。 */
interface EditStep {
  uid: number
  goal: string
  result: string
  method_type_id: number | null
  method_hint: string | null
  is_key: boolean
  uses_elements: number[]
  uses_asks: number[]
  uses_steps: number[]
  answers: number[]
  misconceptions: SolutionMisconception[]
}

// region 状态

const view = ref<SolutionView | null>(null)
const types = ref<StructType[]>([])
const canEdit = ref(false)
const loading = ref(false)
const busy = ref(false)
const solutionNo = ref(props.initialSolutionNo)
const showing = ref<'draft' | 'accepted'>(props.preferRun)
const editing = ref(false)
const editSteps = ref<EditStep[]>([])
let nextUid = 1
let pollTimer: ReturnType<typeof setInterval> | null = null

// endregion

// region 计算属性

const entry = computed(() => view.value?.solutions.find(s => s.solution_no === solutionNo.value) ?? null)
const run = computed<SolutionRun | null>(() => {
  const e = entry.value
  if (!e) return null
  if (showing.value === 'accepted') return e.accepted ?? e.draft
  return e.draft ?? e.accepted
})
const hasBoth = computed(() => !!entry.value?.draft && !!entry.value?.accepted)
const isDraft = computed(() => run.value?.state === 'draft')
const writable = computed(() => canEdit.value && !!view.value?.stem && !view.value.stem.stale)
const solutionNumbers = computed(() => {
  const numbers = new Set(view.value?.solutions.map(s => s.solution_no) ?? [])
  numbers.add(solutionNo.value)
  return [...numbers].sort((a, b) => a - b)
})

/** 题干条目编号:条件 id → "C1",设问 id → "Q1"。 */
const elementLabel = computed(() => new Map(view.value?.stem?.elements.map((e, i) => [e.id, `C${i + 1}`]) ?? []))
const askLabel = computed(() => new Map(view.value?.stem?.asks.map((a, i) => [a.id, `Q${i + 1}`]) ?? []))
const contentOf = computed(() => {
  const map = new Map<string, string>()
  view.value?.stem?.elements.forEach((e, i) => map.set(`C${i + 1}`, e.content))
  view.value?.stem?.asks.forEach((a, i) => map.set(`Q${i + 1}`, a.content))
  return map
})

const stepIssues = computed(() => {
  const map = new Map<number, StructCheckIssue[]>()
  for (const issue of run.value?.check_report?.issues ?? []) {
    if (issue.target === 'step' && issue.index != null) map.set(issue.index, [...(map.get(issue.index) ?? []), issue])
  }
  return map
})
const solutionIssues = computed(() => (run.value?.check_report?.issues ?? []).filter(i => i.target == null && i.severity !== 'info'))

// endregion

// region 公共方法(审核页的快捷键也会调用)

async function load(): Promise<void> {
  loading.value = true
  try {
    const result = await api.getSolution(props.questionId)
    applyView(result)
    if (types.value.length === 0 || !canEdit.value) {
      const subjectId = result.subject_id
      if (subjectId != null) {
        const [typeList, settings] = await Promise.all([api.listTypes(subjectId), api.getSettings(subjectId)])
        types.value = typeList.items
        canEdit.value = !!settings.can_edit
      }
    }
  } catch (e) {
    toast.error(t('structure.panel.loadFailed'), { description: getApiErrorDetail(e, '') })
  } finally {
    loading.value = false
  }
}

async function redecompose(): Promise<void> {
  if (!writable.value || busy.value) return
  busy.value = true
  try {
    const result = await api.decomposeSolutions([props.questionId], solutionNo.value)
    if (!result.queued.length) {
      toast.error(t('structure.solution.queueSkipped'))
      return
    }
    toast.success(t('structure.panel.decomposeQueued'))
    applyView(await api.getSolution(props.questionId))
  } catch (e) {
    toast.error(t('structure.panel.decomposeFailed'), { description: getApiErrorDetail(e, '') })
  } finally {
    busy.value = false
  }
}

async function accept(): Promise<void> {
  await reviewCurrent('accept')
}

async function reject(): Promise<void> {
  await reviewCurrent('reject')
}

function startEdit(): void {
  if (!writable.value) return
  const steps = run.value?.steps ?? []
  const uids = steps.map(() => nextUid++)
  editSteps.value = steps.map((step, index) => ({
    uid: uids[index]!,
    goal: step.goal,
    result: step.result ?? '',
    method_type_id: step.method_type_id,
    method_hint: step.method_hint,
    is_key: step.is_key,
    uses_elements: [...step.uses_elements],
    uses_asks: [...step.uses_asks],
    uses_steps: step.uses_steps.map(i => uids[i]!).filter(uid => uid != null),
    answers: [...step.answers],
    misconceptions: step.misconceptions.map(m => ({ ...m })),
  }))
  if (!editSteps.value.length) addStep()
  editing.value = true
}

function cancelEdit(): void {
  editing.value = false
}

async function saveEdit(acceptNow: boolean): Promise<void> {
  if (busy.value) return
  if (editSteps.value.some(step => !step.goal.trim())) {
    toast.error(t('structure.solution.emptyGoal'))
    return
  }
  busy.value = true
  try {
    const indexOf = new Map(editSteps.value.map((step, index) => [step.uid, index]))
    const result = await api.saveSolution({
      question_id: props.questionId,
      solution_no: solutionNo.value,
      accept: acceptNow,
      steps: editSteps.value.map((step, index) => ({
        goal: step.goal.trim(),
        result: step.result.trim() || null,
        method_type_id: step.method_type_id,
        method_hint: step.method_type_id ? null : step.method_hint,
        is_key: step.is_key,
        uses_elements: step.uses_elements,
        uses_asks: step.uses_asks,
        uses_steps: step.uses_steps.map(uid => indexOf.get(uid)).filter((i): i is number => i != null && i < index),
        answers: step.answers,
        misconceptions: step.misconceptions.filter(m => m.description.trim()),
      })),
    })
    editing.value = false
    showing.value = acceptNow ? 'accepted' : 'draft'
    applyView(result)
    toast.success(t(acceptNow ? 'structure.panel.savedAccepted' : 'structure.panel.saved'))
    emit('changed')
  } catch (e) {
    toast.error(t('common.saveFailed'), { description: getApiErrorDetail(e, '') })
  } finally {
    busy.value = false
  }
}

defineExpose({ accept, reject, startEdit, redecompose, reload: load, isDraft, editing })

// endregion

// region 事件处理:编辑

function addStep(): void {
  editSteps.value.push({
    uid: nextUid++, goal: '', result: '', method_type_id: null, method_hint: null, is_key: false,
    uses_elements: [], uses_asks: [], uses_steps: [], answers: [], misconceptions: [],
  })
}

function moveStep(index: number, delta: -1 | 1): void {
  const target = index + delta
  if (target < 0 || target >= editSteps.value.length) return
  const [step] = editSteps.value.splice(index, 1)
  editSteps.value.splice(target, 0, step!)
}

function removeStep(index: number): void {
  const [removed] = editSteps.value.splice(index, 1)
  if (!removed) return
  for (const step of editSteps.value) step.uses_steps = step.uses_steps.filter(uid => uid !== removed.uid)
}

function toggle(list: number[], value: number, checked: boolean | 'indeterminate'): void {
  const index = list.indexOf(value)
  if (checked === true && index < 0) list.push(value)
  if (checked !== true && index >= 0) list.splice(index, 1)
}

/** 新增一种解法(编号取当前最大 + 1),直接进入编辑。 */
function addSolution(): void {
  solutionNo.value = Math.max(0, ...solutionNumbers.value) + 1
  startEdit()
}

// endregion

// region 内部辅助函数

function applyView(next: SolutionView): void {
  const hadJob = !!view.value?.job
  view.value = next
  if (next.job) startPolling()
  else {
    stopPolling()
    if (hadJob) emit('changed')
  }
}

function startPolling(): void {
  if (pollTimer) return
  pollTimer = setInterval(async () => {
    try {
      applyView(await api.getSolution(props.questionId))
    } catch {
      stopPolling()
    }
  }, 3000)
}

function stopPolling(): void {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = null
}

async function reviewCurrent(action: 'accept' | 'reject'): Promise<void> {
  const current = run.value
  if (!current || current.state !== 'draft' || busy.value) return
  busy.value = true
  try {
    await api.reviewSolutions([current.id], action)
    toast.success(t(action === 'accept' ? 'structure.panel.accepted' : 'structure.panel.rejected'))
    showing.value = action === 'accept' ? 'accepted' : 'draft'
    applyView(await api.getSolution(props.questionId))
    emit('changed')
  } catch (e) {
    toast.error(t('structure.panel.reviewFailed'), { description: getApiErrorDetail(e, '') })
  } finally {
    busy.value = false
  }
}

function issueText(issue: StructCheckIssue): string {
  const key = `structure.solution.codes.${issue.code}`
  const text = t(key, { detail: issue.detail })
  return text === key ? issue.message : text
}

function methodLabel(path: string[]): string {
  return path.slice(1).join(' › ') || path.join(' › ')
}

// endregion

watch(() => [props.questionId, props.initialSolutionNo], () => {
  editing.value = false
  solutionNo.value = props.initialSolutionNo
  showing.value = props.preferRun
  void load()
}, { immediate: true })
onBeforeUnmount(stopPolling)
</script>

<template>
  <div class="space-y-4">
    <div v-if="loading && !view" class="flex items-center gap-2 py-10 text-sm text-muted-foreground">
      <Loader2 class="h-4 w-4 animate-spin" /> {{ t('common.loading') }}
    </div>

    <template v-else-if="view">
      <!-- 依据的题干 -->
      <div v-if="!view.stem" class="rounded-md border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">
        {{ t('structure.solution.needsStem') }}
      </div>
      <template v-else>
        <div v-if="view.stem.stale" class="flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm">
          <TriangleAlert class="h-4 w-4 text-destructive" /> {{ t('structure.solution.stemStale') }}
        </div>
        <details class="rounded-md border bg-muted/30 px-3 py-2 text-sm" open>
          <summary class="cursor-pointer text-xs text-muted-foreground">{{ t('structure.solution.stemItems') }}</summary>
          <ul class="mt-2 space-y-1">
            <li v-for="(e, i) in view.stem.elements" :key="`c${e.id}`" class="flex gap-2">
              <span class="w-7 shrink-0 font-mono text-xs text-muted-foreground">C{{ i + 1 }}</span><MathText :text="e.content" />
            </li>
            <li v-for="(a, i) in view.stem.asks" :key="`q${a.id}`" class="flex gap-2">
              <span class="w-7 shrink-0 font-mono text-xs text-muted-foreground">Q{{ i + 1 }}</span><MathText :text="a.content" />
            </li>
          </ul>
        </details>

        <!-- 解法切换与操作 -->
        <div class="flex flex-wrap items-center gap-2">
          <div class="inline-flex overflow-hidden rounded-md border text-xs">
            <button
              v-for="no in solutionNumbers"
              :key="no"
              type="button"
              :disabled="editing"
              :class="cn('px-2 py-0.5', no !== solutionNumbers[0] && 'border-l', solutionNo === no ? 'bg-accent font-medium' : 'text-muted-foreground')"
              @click="solutionNo = no"
            >{{ t('structure.solution.method', { no }) }}</button>
          </div>
          <Button v-if="writable && !editing" size="sm" variant="ghost" class="h-7 px-2" @click="addSolution">
            <Plus class="mr-1 h-3.5 w-3.5" />{{ t('structure.solution.addMethod') }}
          </Button>
          <template v-if="run">
            <Badge variant="outline" :class="isDraft ? 'border-amber-500/50 text-amber-700 dark:text-amber-300' : 'border-emerald-500/40 text-emerald-700 dark:text-emerald-300'">
              {{ t(`structure.runStates.${run.state}`) }}
            </Badge>
            <Badge v-if="run.stale" variant="outline" class="border-destructive/40 text-destructive">{{ t('structure.solution.stale') }}</Badge>
            <Badge v-if="run.thinking_load != null" variant="secondary">{{ t('structure.solution.thinkingLoad', { value: formatNumber(run.thinking_load) }) }}</Badge>
            <span class="text-xs text-muted-foreground">
              {{ t(`structure.origins.${run.origin}`) }}<template v-if="run.model"> · {{ run.model }}</template> · {{ formatDateTime(run.created_at) }}
            </span>
            <div v-if="hasBoth && !editing" class="inline-flex overflow-hidden rounded-md border text-xs">
              <button type="button" :class="cn('px-2 py-0.5', showing === 'draft' ? 'bg-accent font-medium' : 'text-muted-foreground')" @click="showing = 'draft'">{{ t('structure.runStates.draft') }}</button>
              <button type="button" :class="cn('border-l px-2 py-0.5', showing === 'accepted' ? 'bg-accent font-medium' : 'text-muted-foreground')" @click="showing = 'accepted'">{{ t('structure.runStates.accepted') }}</button>
            </div>
          </template>
          <div v-if="writable && !editing" class="ml-auto flex flex-wrap gap-2">
            <Button v-if="run && isDraft" size="sm" :disabled="busy" @click="accept"><Check class="mr-1 h-4 w-4" />{{ t('structure.panel.accept') }}</Button>
            <Button v-if="run && isDraft" size="sm" variant="outline" :disabled="busy" @click="reject"><X class="mr-1 h-4 w-4" />{{ t('structure.panel.reject') }}</Button>
            <Button v-if="run" size="sm" variant="outline" :disabled="busy" @click="startEdit"><Pencil class="mr-1 h-4 w-4" />{{ t('structure.panel.edit') }}</Button>
            <Button size="sm" :variant="run ? 'ghost' : 'default'" :disabled="busy || !!view.job" @click="redecompose">
              <RefreshCw v-if="run" class="mr-1 h-4 w-4" /><Sparkles v-else class="mr-1 h-4 w-4" />
              {{ run ? t('structure.solution.redecompose') : t('structure.solution.decompose') }}
            </Button>
          </div>
          <div v-if="editing" class="ml-auto flex flex-wrap gap-2">
            <Button size="sm" :disabled="busy" @click="saveEdit(true)"><Check class="mr-1 h-4 w-4" />{{ t('structure.panel.saveAndAccept') }}</Button>
            <Button size="sm" variant="outline" :disabled="busy" @click="saveEdit(false)">{{ t('structure.panel.saveDraft') }}</Button>
            <Button size="sm" variant="ghost" :disabled="busy" @click="cancelEdit">{{ t('common.cancel') }}</Button>
          </div>
        </div>

        <div v-if="view.job" class="flex items-center gap-2 rounded-md border border-primary/30 bg-primary/5 px-3 py-2 text-sm">
          <Loader2 v-if="view.job.status !== 'paused'" class="h-4 w-4 animate-spin text-primary" />
          <TriangleAlert v-else class="h-4 w-4 text-amber-600" />
          <span>{{ view.job.status === 'paused' ? t('structure.panel.jobPaused', { reason: t(`structure.pausedReasons.${view.job.paused_reason ?? 'unavailable'}`) }) : t('structure.solution.jobRunning') }}</span>
        </div>

        <p v-if="!run && !editing && !view.job" class="py-4 text-center text-sm text-muted-foreground">
          {{ t('structure.solution.empty') }}
        </p>

        <!-- 查看 -->
        <template v-if="run && !editing">
          <ul v-if="solutionIssues.length" class="space-y-0.5 text-xs text-destructive">
            <li v-for="(issue, i) in solutionIssues" :key="i">{{ issueText(issue) }}</li>
          </ul>
          <ol class="space-y-2">
            <li v-for="(step, index) in run.steps" :key="step.id" :class="cn('rounded-md border px-3 py-2', step.is_key && 'border-primary/50 bg-primary/5')">
              <div class="flex items-start gap-2 text-sm">
                <span class="mt-0.5 w-7 shrink-0 font-mono text-xs text-muted-foreground">S{{ index + 1 }}</span>
                <div class="min-w-0 flex-1 space-y-1">
                  <div class="flex items-start gap-1.5">
                    <Star v-if="step.is_key" class="mt-0.5 h-3.5 w-3.5 shrink-0 fill-primary text-primary" :title="t('structure.solution.key')" />
                    <MathText :text="step.goal" />
                  </div>
                  <div class="flex flex-wrap items-center gap-1.5 text-xs">
                    <span v-if="step.method_path.length" class="rounded border border-primary/40 px-1.5 py-0.5 text-primary">
                      {{ methodLabel(step.method_path) }}<template v-if="step.weight !== 1"> ×{{ formatNumber(step.weight) }}</template>
                    </span>
                    <span v-else-if="step.method_hint" class="italic text-muted-foreground">{{ t('structure.panel.unclassifiedHint', { hint: step.method_hint }) }}</span>
                    <span
                      v-for="id in step.uses_elements" :key="`e${id}`"
                      class="rounded bg-muted px-1.5 py-0.5 font-mono" :title="contentOf.get(elementLabel.get(id) ?? '')"
                    >{{ elementLabel.get(id) ?? '?' }}</span>
                    <span
                      v-for="id in step.uses_asks" :key="`a${id}`"
                      class="rounded bg-muted px-1.5 py-0.5 font-mono" :title="contentOf.get(askLabel.get(id) ?? '')"
                    >{{ askLabel.get(id) ?? '?' }}</span>
                    <span v-for="i in step.uses_steps" :key="`s${i}`" class="rounded bg-muted px-1.5 py-0.5 font-mono">S{{ i + 1 }}</span>
                    <span v-for="id in step.answers" :key="`ans${id}`" class="rounded bg-emerald-500/10 px-1.5 py-0.5 font-mono text-emerald-700 dark:text-emerald-300">
                      {{ t('structure.solution.answers', { ask: askLabel.get(id) ?? '?' }) }}
                    </span>
                  </div>
                  <p v-if="step.result" class="text-sm"><span class="text-muted-foreground">⇒ </span><MathText :text="step.result" /></p>
                  <ul v-if="step.misconceptions.length" class="space-y-0.5 text-xs text-amber-700 dark:text-amber-300">
                    <li v-for="(m, mi) in step.misconceptions" :key="mi">
                      <TriangleAlert class="mr-1 inline h-3 w-3" /><MathText :text="m.description" />
                    </li>
                  </ul>
                  <p
                    v-for="(issue, ii) in (stepIssues.get(index) ?? []).filter(i => !(i.code === 'no_method' && step.method_hint))" :key="ii"
                    :class="cn('text-xs', issue.severity === 'error' ? 'text-destructive' : 'text-amber-700 dark:text-amber-300')"
                  >{{ issueText(issue) }}</p>
                </div>
              </div>
            </li>
          </ol>
        </template>

        <!-- 编辑 -->
        <template v-if="editing">
          <ol class="space-y-2">
            <li v-for="(step, index) in editSteps" :key="step.uid" class="space-y-2 rounded-md border px-3 py-2">
              <div class="flex items-start gap-2">
                <span class="mt-2 w-7 shrink-0 font-mono text-xs text-muted-foreground">S{{ index + 1 }}</span>
                <div class="min-w-0 flex-1 space-y-2">
                  <Textarea v-model="step.goal" rows="2" class="min-h-[2.5rem] text-sm" :placeholder="t('structure.solution.goalPlaceholder')" />
                  <Textarea v-model="step.result" rows="1" class="min-h-[2rem] text-sm" :placeholder="t('structure.solution.resultPlaceholder')" />
                  <div class="flex flex-wrap items-center gap-2">
                    <div class="w-56">
                      <StructTypeSelect v-model="step.method_type_id" :types="types" kind="method" trigger-class="h-8" />
                    </div>
                    <Input
                      v-if="!step.method_type_id"
                      :model-value="step.method_hint ?? ''"
                      class="h-8 w-40 text-xs"
                      :placeholder="t('structure.solution.hintPlaceholder')"
                      @update:model-value="step.method_hint = String($event) || null"
                    />
                    <label class="flex items-center gap-1 text-xs">
                      <Checkbox :model-value="step.is_key" @update:model-value="step.is_key = $event === true" />{{ t('structure.solution.key') }}
                    </label>
                  </div>
                  <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                    <span class="text-muted-foreground">{{ t('structure.solution.uses') }}</span>
                    <label v-for="(e, i) in view.stem.elements" :key="`ue${e.id}`" class="flex items-center gap-1" :title="e.content">
                      <Checkbox :model-value="step.uses_elements.includes(e.id)" @update:model-value="toggle(step.uses_elements, e.id, $event)" />C{{ i + 1 }}
                    </label>
                    <label v-for="(a, i) in view.stem.asks" :key="`ua${a.id}`" class="flex items-center gap-1" :title="a.content">
                      <Checkbox :model-value="step.uses_asks.includes(a.id)" @update:model-value="toggle(step.uses_asks, a.id, $event)" />Q{{ i + 1 }}
                    </label>
                    <label v-for="(prev, pi) in editSteps.slice(0, index)" :key="`us${prev.uid}`" class="flex items-center gap-1">
                      <Checkbox :model-value="step.uses_steps.includes(prev.uid)" @update:model-value="toggle(step.uses_steps, prev.uid, $event)" />S{{ pi + 1 }}
                    </label>
                  </div>
                  <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                    <span class="text-muted-foreground">{{ t('structure.solution.answersLabel') }}</span>
                    <label v-for="(a, i) in view.stem.asks" :key="`an${a.id}`" class="flex items-center gap-1" :title="a.content">
                      <Checkbox :model-value="step.answers.includes(a.id)" @update:model-value="toggle(step.answers, a.id, $event)" />Q{{ i + 1 }}
                    </label>
                  </div>
                  <div class="space-y-1">
                    <div v-for="(m, mi) in step.misconceptions" :key="mi" class="flex items-center gap-2">
                      <Input v-model="m.description" class="h-8 flex-1 text-xs" :placeholder="t('structure.solution.misconceptionPlaceholder')" />
                      <NativeSelect v-model="m.source" class="h-8 w-28">
                        <NativeSelectOption value="distractor">{{ t('structure.solution.sources.distractor') }}</NativeSelectOption>
                        <NativeSelectOption value="response">{{ t('structure.solution.sources.response') }}</NativeSelectOption>
                      </NativeSelect>
                      <Button size="icon" variant="ghost" class="h-7 w-7" @click="step.misconceptions.splice(mi, 1)"><Trash2 class="h-3.5 w-3.5" /></Button>
                    </div>
                    <Button size="sm" variant="ghost" class="h-7 px-2 text-xs" @click="step.misconceptions.push({ description: '', source: 'distractor' })">
                      + {{ t('structure.solution.addMisconception') }}
                    </Button>
                  </div>
                </div>
                <div class="flex shrink-0 flex-col gap-0.5">
                  <Button size="icon" variant="ghost" class="h-6 w-6" :title="t('structure.panel.moveUp')" @click="moveStep(index, -1)"><ArrowUp class="h-3.5 w-3.5" /></Button>
                  <Button size="icon" variant="ghost" class="h-6 w-6" :title="t('structure.panel.moveDown')" @click="moveStep(index, 1)"><ArrowDown class="h-3.5 w-3.5" /></Button>
                  <Button size="icon" variant="ghost" class="h-6 w-6 text-destructive" :title="t('common.delete')" @click="removeStep(index)"><Trash2 class="h-3.5 w-3.5" /></Button>
                </div>
              </div>
            </li>
          </ol>
          <Button size="sm" variant="outline" @click="addStep"><Plus class="mr-1 h-4 w-4" />{{ t('structure.solution.addStep') }}</Button>
        </template>
      </template>
    </template>
  </div>
</template>
