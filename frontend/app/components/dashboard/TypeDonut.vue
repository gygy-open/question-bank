<script setup lang="ts">
import { Donut } from '@unovis/ts'
import { VisDonut, VisSingleContainer, VisTooltip } from '@unovis/vue'
import { ChartContainer, type ChartConfig } from '@/components/ui/chart'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { formatNumber } from '@/lib/locale'
import { chartColor, QUESTION_TYPE_LABEL_KEYS, tooltipHtml } from '@/lib/dashboard'
import type { DashboardCountItem } from '~/types/dashboard'

const props = defineProps<{ items: DashboardCountItem[]; total: number }>()
const { t, te } = useI18n()

interface Segment {
  key: string
  label: string
  count: number
  color: string
}

const segments = computed<Segment[]>(() =>
  props.items.map((item, i) => {
    const labelKey = QUESTION_TYPE_LABEL_KEYS[item.key]
    return {
      key: item.key,
      label: labelKey && te(labelKey) ? t(labelKey) : item.key,
      count: item.count,
      color: chartColor(i),
    }
  }),
)
const visible = computed(() => segments.value.filter(s => s.count > 0))
const config = computed<ChartConfig>(() =>
  Object.fromEntries(segments.value.map(s => [s.key, { label: s.label, color: s.color }])),
)
const percent = (n: number) => (props.total ? Math.round((n / props.total) * 100) : 0)

const triggers = {
  [Donut.selectors.segment]: (d: { data: Segment }) =>
    tooltipHtml(null, [{ color: d.data.color, label: d.data.label, value: `${formatNumber(d.data.count)} · ${percent(d.data.count)}%` }]),
}
</script>

<template>
  <Card class="gap-4">
    <CardHeader>
      <CardTitle>{{ t('dashboard.distribution.typeTitle') }}</CardTitle>
      <CardDescription>{{ t('dashboard.distribution.typeDescription') }}</CardDescription>
    </CardHeader>
    <CardContent class="flex flex-col items-center gap-6 sm:flex-row lg:flex-col 2xl:flex-row">
      <ChartContainer :config="config" class="aspect-square h-[180px] w-[180px] shrink-0">
        <VisSingleContainer :data="visible">
          <VisDonut
            :value="(d: Segment) => d.count"
            :color="(d: Segment) => d.color"
            :arc-width="26"
            :pad-angle="0.02"
            :corner-radius="4"
            :central-label="formatNumber(total)"
            :central-sub-label="t('dashboard.distribution.questions')"
          />
          <VisTooltip :triggers="triggers" />
        </VisSingleContainer>
      </ChartContainer>
      <ul class="grid w-full gap-2 text-sm">
        <li v-for="s in segments" :key="s.key" class="flex items-center gap-2" :class="s.count ? '' : 'opacity-50'">
          <span class="size-2.5 shrink-0 rounded-[2px]" :style="{ background: s.color }" />
          <span class="text-muted-foreground truncate">{{ s.label }}</span>
          <span class="ml-auto font-medium tabular-nums">{{ formatNumber(s.count) }}</span>
          <span class="text-muted-foreground w-10 text-right text-xs tabular-nums">{{ percent(s.count) }}%</span>
        </li>
      </ul>
    </CardContent>
  </Card>
</template>
