<script setup lang="ts">
import { StackedBar } from '@unovis/ts'
import { VisAxis, VisStackedBar, VisTooltip, VisXYContainer } from '@unovis/vue'
import { ChartContainer, type ChartConfig } from '@/components/ui/chart'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { formatNumber } from '@/lib/locale'
import { STATUS_COLORS, tooltipHtml } from '@/lib/dashboard'
import type { DashboardDistribution } from '~/types/dashboard'

const props = defineProps<{ distribution: DashboardDistribution; total: number }>()
const { t, te } = useI18n()

const percent = (n: number) => (props.total ? (n / props.total) * 100 : 0)

const statuses = computed(() =>
  props.distribution.status.map(s => ({
    ...s,
    label: te(`questions.statuses.${s.key}`) ? t(`questions.statuses.${s.key}`) : s.key,
    color: STATUS_COLORS[s.key] ?? 'var(--chart-5)',
  })),
)

const visibility = computed(() => {
  const map = Object.fromEntries(props.distribution.visibility.map(v => [v.key, v.count]))
  return { public: map.public ?? 0, private: map.private ?? 0 }
})

interface DifficultyBar { level: number; count: number }
const difficulty = computed<DifficultyBar[]>(() =>
  props.distribution.difficulty.map(d => ({ level: Number(d.key), count: d.count })),
)
const DIFFICULTY_COLOR = 'var(--chart-2)'
const difficultyConfig = computed<ChartConfig>(() => ({
  count: { label: t('dashboard.distribution.questions'), color: DIFFICULTY_COLOR },
}))
const levelLabel = (level: number) => t('dashboard.distribution.level', { level })
const difficultyTriggers = computed(() => ({
  [StackedBar.selectors.bar]: (d: DifficultyBar) =>
    tooltipHtml(levelLabel(d.level), [{ color: DIFFICULTY_COLOR, label: t('dashboard.distribution.questions'), value: formatNumber(d.count) }]),
}))
const averageDifficulty = computed(() => {
  const n = difficulty.value.reduce((s, d) => s + d.count, 0)
  if (!n) return '-'
  return formatNumber(difficulty.value.reduce((s, d) => s + d.level * d.count, 0) / n, { maximumFractionDigits: 1 })
})
</script>

<template>
  <Card class="gap-4">
    <CardHeader>
      <CardTitle>{{ t('dashboard.distribution.qualityTitle') }}</CardTitle>
      <CardDescription>{{ t('dashboard.distribution.qualityDescription') }}</CardDescription>
    </CardHeader>
    <CardContent class="grid gap-6">
      <section class="grid gap-2">
        <h4 class="text-sm font-medium">{{ t('dashboard.distribution.statusTitle') }}</h4>
        <div class="bg-muted flex h-3 w-full overflow-hidden rounded-full">
          <Tooltip v-for="s in statuses.filter(s => s.count > 0)" :key="s.key">
            <TooltipTrigger as-child>
              <div class="h-full transition-[width]" :style="{ width: `${percent(s.count)}%`, background: s.color }" />
            </TooltipTrigger>
            <TooltipContent>{{ s.label }} · {{ formatNumber(s.count) }}</TooltipContent>
          </Tooltip>
        </div>
        <ul class="grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-4">
          <li v-for="s in statuses" :key="s.key" class="flex items-center gap-1.5">
            <span class="size-2 shrink-0 rounded-full" :style="{ background: s.color }" />
            <span class="text-muted-foreground">{{ s.label }}</span>
            <span class="ml-auto font-medium tabular-nums">{{ formatNumber(s.count) }}</span>
          </li>
        </ul>
      </section>

      <section class="grid gap-2">
        <div class="flex items-baseline justify-between">
          <h4 class="text-sm font-medium">{{ t('dashboard.distribution.difficultyTitle') }}</h4>
          <span class="text-muted-foreground text-xs">{{ t('dashboard.distribution.averageDifficulty', { value: averageDifficulty }) }}</span>
        </div>
        <ChartContainer :config="difficultyConfig" class="aspect-auto h-[140px]">
          <VisXYContainer :data="difficulty" :margin="{ left: 4, right: 4 }">
            <VisStackedBar
              :x="(d: DifficultyBar) => d.level"
              :y="(d: DifficultyBar) => d.count"
              :color="DIFFICULTY_COLOR"
              :rounded-corners="4"
              :bar-padding="0.25"
            />
            <VisAxis
              type="x"
              :tick-line="false"
              :domain-line="false"
              :grid-line="false"
              :tick-values="[1, 2, 3, 4, 5]"
              :tick-format="levelLabel"
            />
            <VisTooltip :triggers="difficultyTriggers" />
          </VisXYContainer>
        </ChartContainer>
      </section>

      <section class="grid gap-2">
        <h4 class="text-sm font-medium">{{ t('dashboard.distribution.visibilityTitle') }}</h4>
        <div class="flex items-center gap-3 text-xs">
          <span class="text-muted-foreground shrink-0">{{ t('dashboard.distribution.public') }} {{ formatNumber(visibility.public) }}</span>
          <div class="bg-muted flex h-2 flex-1 overflow-hidden rounded-full">
            <div class="bg-primary h-full" :style="{ width: `${percent(visibility.public)}%` }" />
          </div>
          <span class="text-muted-foreground shrink-0">{{ t('dashboard.distribution.private') }} {{ formatNumber(visibility.private) }}</span>
        </div>
      </section>
    </CardContent>
  </Card>
</template>
