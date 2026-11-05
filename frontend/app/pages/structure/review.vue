<script setup lang="ts">
/**
 * 拆解审核页(规格 §8.2):当前学科的待审拆解队列 + 右侧题干结构面板。
 * 顶部切换「题干」/「解答」两个队列(解答结构为三期,右侧换成解答面板)。
 *
 * - 队列默认把有体检错误的排在前面,可按体检结果、来源、对象筛选;
 * - 快捷键:J / K 下一条 / 上一条,A 采纳,X 驳回,E 编辑,R 重新拆解(输入框聚焦时不触发);
 * - 可勾选没有错误的拆解批量采纳;
 * - 审核或保存后刷新队列,并自动选中下一条。
 */
import { computed, onActivated, ref, watch } from 'vue'
import { onKeyStroke } from '@vueuse/core'
import { toast } from 'vue-sonner'
import { CheckCheck, Inbox, Loader2 } from '@lucide/vue'
import PageHeader from '@/components/PageHeader.vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import MathText from '@/components/structure/MathText.vue'
import StructurePanel from '@/components/structure/StructurePanel.vue'
import SolutionPanel from '@/components/structure/SolutionPanel.vue'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { getApiErrorDetail } from '@/lib/apiErrors'
import { cn } from '@/lib/utils'
import type { StructOrigin, StructReviewQueueItem } from '~/types'

const { t } = useI18n()
const api = useStructure()
const { currentSubjectId } = useSubjectContext()

const PAGE_SIZE = 20

// region 状态

const items = ref<StructReviewQueueItem[]>([])
const total = ref(0)
const page = ref(1)
const pages = ref(0)
const loading = ref(false)
const busy = ref(false)

// 审核哪一种:题干拆解或解答拆解。
const mode = ref<'stem' | 'solution'>('stem')
// 筛选:空字符串表示「全部」(不传给后端)。
const check = ref<'' | 'errors' | 'warnings' | 'clean'>('')
const origin = ref<'' | StructOrigin>('')
const targetType = ref<'' | 'question' | 'stimulus'>('')

/** 当前选中的队列项(用 run id 标识,刷新队列后仍能找回位置)。 */
const selectedRunId = ref<number | null>(null)
/** 批量采纳勾选的 run id。 */
const checked = ref<Set<number>>(new Set())

// 右侧面板(题干或解答),两者暴露同一组方法供快捷键调用。
const panel = ref<InstanceType<typeof StructurePanel> | InstanceType<typeof SolutionPanel> | null>(null)

// endregion

// region 计算属性

const selected = computed(() => items.value.find(item => item.id === selectedRunId.value) ?? null)
const selectedIndex = computed(() => items.value.findIndex(item => item.id === selectedRunId.value))

const checkOptions = computed(() => [
  { value: '', label: t('structure.review.allChecks') },
  { value: 'errors', label: t('structure.review.withErrors') },
  { value: 'warnings', label: t('structure.review.withWarnings') },
  { value: 'clean', label: t('structure.review.clean') },
])
const originOptions = computed(() => [
  { value: '', label: t('structure.review.allOrigins') },
  { value: 'ai', label: t('structure.origins.ai') },
  { value: 'human', label: t('structure.origins.human') },
  { value: 'agent', label: t('structure.origins.agent') },
])
const targetOptions = computed(() => [
  { value: '', label: t('structure.review.allTargets') },
  { value: 'question', label: t('structure.review.questions') },
  { value: 'stimulus', label: t('structure.review.materials') },
])

// 只有没有体检错误的才允许批量采纳;有错误的必须逐条看过。
const batchable = computed(() => items.value.filter(item => item.check_errors === 0))
const allBatchChecked = computed(() => batchable.value.length > 0 && batchable.value.every(item => checked.value.has(item.id)))

// endregion

// region 公共方法 / 事件处理

/** 加载队列;keepSelection 时尽量保持当前选中,否则选第一条。 */
async function loadQueue(keepSelection = true): Promise<void> {
  if (currentSubjectId.value == null) return
  loading.value = true
  try {
    const query: Record<string, unknown> = { page: page.value, size: PAGE_SIZE }
    if (check.value) query.check = check.value
    if (mode.value === 'stem' && origin.value) query.origin = origin.value
    if (mode.value === 'stem' && targetType.value) query.target_type = targetType.value
    const result = mode.value === 'stem'
      ? await api.reviewQueue(currentSubjectId.value, query)
      : await api.solutionReviewQueue(currentSubjectId.value, query)
    // 当前页被审完变空了:退回上一页。
    if (!result.items.length && page.value > 1) {
      page.value -= 1
      return
    }
    items.value = result.items
    total.value = result.total
    pages.value = result.pages
    checked.value = new Set([...checked.value].filter(id => result.items.some(item => item.id === id)))
    if (!keepSelection || !result.items.some(item => item.id === selectedRunId.value)) {
      selectedRunId.value = result.items[0]?.id ?? null
    }
  } catch (e) {
    toast.error(t('structure.review.loadFailed'), { description: getApiErrorDetail(e, '') })
  } finally {
    loading.value = false
  }
}

/**
 * 面板里完成了审核 / 保存 / 重新拆解:刷新队列。
 * 当前项已不在队列(被采纳或驳回)时,选中原位置上的下一条,保持连续审核的节奏。
 */
async function onPanelChanged(): Promise<void> {
  const index = selectedIndex.value
  const previous = selectedRunId.value
  await loadQueue(true)
  if (!items.value.some(item => item.id === previous)) {
    selectedRunId.value = items.value[Math.min(Math.max(index, 0), items.value.length - 1)]?.id ?? null
  }
}

function select(offset: 1 | -1): void {
  const next = items.value[selectedIndex.value + offset]
  if (next) selectedRunId.value = next.id
}

function toggleChecked(id: number, value: boolean | 'indeterminate'): void {
  const next = new Set(checked.value)
  if (value === true) next.add(id)
  else next.delete(id)
  checked.value = next
}

function toggleAll(value: boolean | 'indeterminate'): void {
  checked.value = value === true ? new Set(batchable.value.map(item => item.id)) : new Set()
}

async function batchAccept(): Promise<void> {
  if (!checked.value.size || busy.value) return
  busy.value = true
  try {
    const ids = [...checked.value]
    const result = mode.value === 'stem' ? await api.review(ids, 'accept') : await api.reviewSolutions(ids, 'accept')
    toast.success(t('structure.review.batchAccepted', { count: result.updated.length }))
    checked.value = new Set()
    await loadQueue(false)
  } catch (e) {
    toast.error(t('structure.panel.reviewFailed'), { description: getApiErrorDetail(e, '') })
  } finally {
    busy.value = false
  }
}

// endregion

// region 快捷键

/** 焦点在输入框、文本域、下拉框或可编辑区域时不响应快捷键,避免打字时误触。 */
function typing(event: KeyboardEvent): boolean {
  const target = event.target as HTMLElement | null
  if (!target) return false
  return ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) || target.isContentEditable
}

/** 注册单键快捷键:不在输入、没有组合修饰键、面板不在编辑状态时才执行。 */
function shortcut(key: string, action: () => void): void {
  onKeyStroke(key, (event) => {
    if (typing(event) || event.ctrlKey || event.metaKey || event.altKey) return
    // 编辑中不响应:避免在编辑时按 A / X 误采纳、误驳回。
    if (panel.value?.editing) return
    event.preventDefault()
    action()
  })
}

shortcut('j', () => select(1))
shortcut('k', () => select(-1))
shortcut('a', () => { void panel.value?.accept() })
shortcut('x', () => { void panel.value?.reject() })
shortcut('e', () => panel.value?.startEdit())
shortcut('r', () => { void panel.value?.redecompose() })

// endregion

// 筛选变化:回到第一页重新加载(若已在第一页,page 不变,需要手动加载)。
watch(mode, () => {
  selectedRunId.value = null
  checked.value = new Set()
})
watch([check, origin, targetType, mode], () => {
  if (page.value !== 1) page.value = 1
  else void loadQueue(false)
})
watch(page, () => { void loadQueue(false) })
// 切换学科:清空并重新加载。
watch(currentSubjectId, () => {
  selectedRunId.value = null
  checked.value = new Set()
  if (page.value !== 1) page.value = 1
  else void loadQueue(false)
}, { immediate: true })
// 页面被 keep-alive 缓存:重新进入时刷新,以看到新拆完的结果。
onActivated(() => { void loadQueue(true) })
</script>

<template>
  <PageHeader :title="t('structure.review.title')" />

  <div class="flex min-h-0 flex-1 flex-col gap-4 px-4 py-6">
    <p class="text-sm text-muted-foreground">{{ t('structure.review.description') }}</p>

    <div class="flex flex-wrap items-center gap-2">
      <Tabs v-model="mode">
        <TabsList>
          <TabsTrigger value="stem">{{ t('structure.solution.tabStem') }}</TabsTrigger>
          <TabsTrigger value="solution">{{ t('structure.solution.tabSolution') }}</TabsTrigger>
        </TabsList>
      </Tabs>
      <NativeSelect v-model="check" class="h-9 w-36">
        <NativeSelectOption v-for="option in checkOptions" :key="option.value" :value="option.value">{{ option.label }}</NativeSelectOption>
      </NativeSelect>
      <NativeSelect v-if="mode === 'stem'" v-model="origin" class="h-9 w-32">
        <NativeSelectOption v-for="option in originOptions" :key="option.value" :value="option.value">{{ option.label }}</NativeSelectOption>
      </NativeSelect>
      <NativeSelect v-if="mode === 'stem'" v-model="targetType" class="h-9 w-32">
        <NativeSelectOption v-for="option in targetOptions" :key="option.value" :value="option.value">{{ option.label }}</NativeSelectOption>
      </NativeSelect>
      <span class="text-sm text-muted-foreground">{{ t('structure.review.total', { count: total }) }}</span>
      <span class="ml-auto hidden text-xs text-muted-foreground lg:inline">{{ t('structure.review.shortcuts') }}</span>
    </div>

    <div class="grid min-h-[60vh] flex-1 gap-4 lg:grid-cols-[minmax(260px,340px)_1fr]">
      <!-- 左侧队列 -->
      <aside class="flex min-h-0 flex-col rounded-lg border bg-card">
        <div class="flex items-center gap-2 border-b px-3 py-2 text-sm">
          <Checkbox :model-value="allBatchChecked" :disabled="!batchable.length" @update:model-value="toggleAll" />
          <span class="text-muted-foreground">{{ t('structure.review.selectClean') }}</span>
          <Button size="sm" variant="outline" class="ml-auto h-7" :disabled="!checked.size || busy" @click="batchAccept">
            <CheckCheck class="mr-1 h-4 w-4" /> {{ t('structure.review.batchAccept', { count: checked.size }) }}
          </Button>
        </div>
        <div class="min-h-0 flex-1 overflow-y-auto">
          <div v-if="loading && !items.length" class="flex items-center gap-2 p-4 text-sm text-muted-foreground">
            <Loader2 class="h-4 w-4 animate-spin" /> {{ t('common.loading') }}
          </div>
          <div v-else-if="!items.length" class="flex flex-col items-center gap-2 p-8 text-center text-sm text-muted-foreground">
            <Inbox class="h-6 w-6" /> {{ t('structure.review.empty') }}
          </div>
          <div
            v-for="item in items"
            :key="item.id"
            role="button"
            tabindex="0"
            :class="cn('flex w-full cursor-pointer items-start gap-2 border-b px-3 py-2 text-left text-sm hover:bg-accent', item.id === selectedRunId && 'bg-accent')"
            @click="selectedRunId = item.id"
            @keydown.enter="selectedRunId = item.id"
          >
            <Checkbox
              class="mt-0.5"
              :model-value="checked.has(item.id)"
              :disabled="item.check_errors > 0"
              @click.stop
              @update:model-value="(value) => toggleChecked(item.id, value)"
            />
            <div class="min-w-0 flex-1 space-y-1">
              <MathText class="line-clamp-2" :text="item.preview" />
              <div class="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                <Badge v-if="item.check_errors" variant="destructive" class="h-5 px-1.5 font-normal">{{ t('structure.review.errors', { count: item.check_errors }) }}</Badge>
                <Badge v-else-if="item.check_warnings" variant="outline" class="h-5 border-amber-500/50 px-1.5 font-normal text-amber-700 dark:text-amber-300">{{ t('structure.review.warnings', { count: item.check_warnings }) }}</Badge>
                <span>{{ t(`structure.origins.${item.origin}`) }}</span>
                <span v-if="item.target_type === 'stimulus'">· {{ t('structure.review.material') }}</span>
                <span v-if="item.solution_no">· {{ t('structure.solution.method', { no: item.solution_no }) }}</span>
                <span v-if="item.thinking_load != null">· {{ t('structure.solution.thinkingLoad', { value: item.thinking_load }) }}</span>
                <span>· #{{ item.target_id }}</span>
              </div>
            </div>
          </div>
        </div>
        <div v-if="pages > 1" class="flex items-center justify-between border-t px-3 py-2 text-sm">
          <Button size="sm" variant="ghost" :disabled="page <= 1" @click="page -= 1">{{ t('structure.review.prev') }}</Button>
          <span class="text-muted-foreground">{{ page }} / {{ pages }}</span>
          <Button size="sm" variant="ghost" :disabled="page >= pages" @click="page += 1">{{ t('structure.review.next') }}</Button>
        </div>
      </aside>

      <!-- 右侧面板 -->
      <section class="min-h-0 overflow-y-auto rounded-lg border bg-card p-4">
        <SolutionPanel
          v-if="selected && mode === 'solution'"
          :key="`s-${selected.id}`"
          ref="panel"
          :question-id="selected.target_id"
          :initial-solution-no="selected.solution_no ?? 1"
          prefer-run="draft"
          @changed="onPanelChanged"
        />
        <StructurePanel
          v-else-if="selected"
          ref="panel"
          :target-type="selected.target_type"
          :target-id="selected.target_id"
          prefer-run="draft"
          @changed="onPanelChanged"
        />
        <p v-else class="py-10 text-center text-sm text-muted-foreground">{{ t('structure.review.pick') }}</p>
      </section>
    </div>
  </div>
</template>
