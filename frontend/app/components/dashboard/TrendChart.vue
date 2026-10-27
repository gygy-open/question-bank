<script setup lang="ts">
import { VisArea, VisAxis, VisCrosshair, VisLine, VisTooltip, VisXYContainer } from '@unovis/vue'
import { ChartContainer, type ChartConfig } from '@/components/ui/chart'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { formatDate, formatNumber } from '@/lib/locale'
import { tooltipHtml } from '@/lib/dashboard'
import type { DashboardTrendPoint } from '~/types/dashboard'

const props = defineProps<{ trend: DashboardTrendPoint[] }>()
const { t } = useI18n()

type Mode = 'created' | 'total'
const mode = ref<Mode>('created')

const COLOR = 'var(--chart-1)'
const config = computed<ChartConfig>(() => ({
  value: { label: mode.value === 'created' ? t('dashboard.trend.created') : t('dashboard.trend.total'), color: COLOR },
}))

const x = (_: DashboardTrendPoint, i: number) => i
const y = (d: DashboardTrendPoint) => d[mode.value]

const dayLabel = (date: string) => formatDate(date, { month: 'numeric', day: 'numeric', timeZone: 'UTC' })
const tickFormat = (i: number) => {
  const point = props.trend[Math.round(i)]
  return point ? dayLabel(point.date) : ''
}

const integerTick = (v: number) => (Number.isInteger(v) ? formatNumber(v) : '')

const createdSum = computed(() => props.trend.reduce((s, p) => s + p.created, 0))

const crosshairTemplate = (d: DashboardTrendPoint) =>
  tooltipHtml(formatDate(d.date, { dateStyle: 'medium', timeZone: 'UTC' }), [
    { color: COLOR, label: config.value.value!.label as string, value: formatNumber(d[mode.value]) },
  ])
</script>

<template>
  <Card class="gap-4">
    <CardHeader class="flex flex-row items-start justify-between gap-4">
      <div class="grid gap-1.5">
        <CardTitle>{{ t('dashboard.trend.title') }}</CardTitle>
        <CardDescription>
          {{ t('dashboard.trend.description', { count: formatNumber(createdSum) }) }}
        </CardDescription>
      </div>
      <Tabs v-model="mode">
        <TabsList>
          <TabsTrigger value="created">{{ t('dashboard.trend.created') }}</TabsTrigger>
          <TabsTrigger value="total">{{ t('dashboard.trend.total') }}</TabsTrigger>
        </TabsList>
      </Tabs>
    </CardHeader>
    <CardContent>
      <ChartContainer :config="config" class="aspect-auto h-[240px]" cursor>
        <VisXYContainer :data="trend" :margin="{ left: 4, right: 8 }" :y-domain="[0, undefined]">
          <VisArea :x="x" :y="y" :color="COLOR" :opacity="0.18" curve-type="monotoneX" />
          <VisLine :x="x" :y="y" :color="COLOR" :line-width="2" curve-type="monotoneX" />
          <VisAxis
            type="x"
            :x="x"
            :tick-line="false"
            :domain-line="false"
            :grid-line="false"
            :num-ticks="6"
            :tick-format="tickFormat"
          />
          <VisAxis type="y" :num-ticks="4" :tick-line="false" :domain-line="false" :tick-format="integerTick" />
          <VisTooltip />
          <VisCrosshair :template="crosshairTemplate" :color="COLOR" />
        </VisXYContainer>
      </ChartContainer>
    </CardContent>
  </Card>
</template>
