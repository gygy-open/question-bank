<script setup lang="ts">
/**
 * 首页「题干结构化」卡片:当前学科的拆解进度、待审数量、排队数、待归类条目与常见元素类型。
 *
 * 数据独立于首页统计接口(/structure/stats),自带加载与失败处理;refreshKey 变化时刷新。
 */
import { computed, ref, watch } from 'vue'
import { Shapes } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { formatNumber } from '@/lib/locale'
import type { StructState, StructStats } from '~/types'

const props = defineProps<{
  subjectId: number
  /** 首页点「刷新」时递增,触发重新加载。 */
  refreshKey?: number
}>()

const { t } = useI18n()
const api = useStructure()

// region 状态

const stats = ref<StructStats | null>(null)

// 与 StructureStateBadge 一致的配色:未拆解灰、待审琥珀、已采纳绿、已过期红。
const STATE_COLORS: Record<StructState, string> = {
  none: 'bg-muted-foreground/30',
  draft: 'bg-amber-500',
  accepted: 'bg-emerald-500',
  stale: 'bg-destructive',
}
const STATE_ORDER: StructState[] = ['accepted', 'draft', 'stale', 'none']

// endregion

// region 计算属性

/** 分段条:各状态占全部题目的比例。 */
const segments = computed(() => {
  const s = stats.value
  if (!s || !s.total) return []
  return STATE_ORDER.map(state => ({
    state,
    count: s.states[state] ?? 0,
    percent: ((s.states[state] ?? 0) / s.total) * 100,
  }))
})

const maxTypeCount = computed(() => Math.max(1, ...(stats.value?.top_types ?? []).map(item => item.count)))

// endregion

// region 内部辅助函数

async function load(): Promise<void> {
  try {
    stats.value = await api.stats(props.subjectId)
  } catch {
    // 统计失败不影响首页其他内容。
    stats.value = null
  }
}

// endregion

watch(() => [props.subjectId, props.refreshKey], () => { void load() }, { immediate: true })
</script>

<template>
  <Card v-if="stats" class="gap-4">
    <CardHeader>
      <CardTitle class="flex items-center gap-2"><Shapes class="size-4" /> {{ t('structure.dashboard.title') }}</CardTitle>
      <CardDescription>{{ t('structure.dashboard.description') }}</CardDescription>
    </CardHeader>
    <CardContent class="grid gap-6 md:grid-cols-2">
      <div class="grid content-start gap-3">
        <div class="flex h-2.5 overflow-hidden rounded-full bg-muted">
          <div
            v-for="segment in segments"
            :key="segment.state"
            :class="STATE_COLORS[segment.state]"
            :style="{ width: `${segment.percent}%` }"
            :title="`${t(`structure.states.${segment.state}`)}: ${segment.count}`"
          />
        </div>
        <div class="grid grid-cols-2 gap-2 text-sm">
          <div v-for="segment in segments" :key="segment.state" class="flex items-center gap-2">
            <span :class="['size-2 rounded-full', STATE_COLORS[segment.state]]" />
            <span class="text-muted-foreground">{{ t(`structure.states.${segment.state}`) }}</span>
            <span class="ml-auto font-medium tabular-nums">{{ formatNumber(segment.count) }}</span>
          </div>
        </div>
        <div class="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span>{{ t('structure.dashboard.queued', { count: stats.queued }) }}</span>
          <span>{{ t('structure.dashboard.unclassified', { count: stats.unclassified }) }}</span>
          <span v-if="stats.origins">{{ t('structure.dashboard.origins', {
            ai: formatNumber(stats.origins.ai),
            human: formatNumber(stats.origins.human),
            agent: formatNumber(stats.origins.agent),
          }) }}</span>
          <span v-if="stats.types_total">{{ t('structure.dashboard.kpCoverage', { mapped: stats.types_mapped, total: stats.types_total }) }}</span>
          <span v-if="stats.with_thinking">{{ t('structure.dashboard.withThinking', { count: formatNumber(stats.with_thinking) }) }}</span>
        </div>
        <Button
          v-if="stats.states.draft > 0"
          size="sm"
          class="w-fit"
          as-child
        >
          <NuxtLink to="/structure/review">{{ t('structure.dashboard.review', { count: stats.states.draft }) }}</NuxtLink>
        </Button>
      </div>
      <div class="grid content-start gap-2">
        <span class="text-sm font-medium">{{ t('structure.dashboard.topTypes') }}</span>
        <p v-if="!stats.top_types.length" class="text-sm text-muted-foreground">{{ t('structure.dashboard.noTypes') }}</p>
        <div v-for="item in stats.top_types.slice(0, 8)" :key="item.type_id" class="grid gap-1">
          <div class="flex justify-between gap-2 text-xs">
            <span class="truncate" :title="item.path.join(' › ')">{{ item.path.join(' › ') }}</span>
            <span class="shrink-0 tabular-nums text-muted-foreground">{{ item.count }}</span>
          </div>
          <div class="h-1.5 overflow-hidden rounded-full bg-muted">
            <div class="h-full rounded-full bg-primary/70" :style="{ width: `${(item.count / maxTypeCount) * 100}%` }" />
          </div>
        </div>
      </div>
    </CardContent>
  </Card>
</template>
