<script setup lang="ts">
import { CircleDashed, Hash, ListTree } from '@lucide/vue'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { formatNumber } from '@/lib/locale'
import type { DashboardKnowledgeCoverage } from '~/types/dashboard'

const props = defineProps<{ coverage: DashboardKnowledgeCoverage }>()
const { t } = useI18n()

const coveragePercent = computed(() =>
  props.coverage.total ? Math.round((props.coverage.covered / props.coverage.total) * 100) : 0,
)
const maxCount = computed(() => Math.max(1, ...props.coverage.top.map(k => k.count)))
const uncoveredCount = computed(() => props.coverage.total - props.coverage.covered)
</script>

<template>
  <Card class="gap-4">
    <CardHeader>
      <CardTitle>{{ t('dashboard.coverage.title') }}</CardTitle>
      <CardDescription>{{ t('dashboard.coverage.description') }}</CardDescription>
    </CardHeader>
    <CardContent class="grid gap-6">
      <div v-if="coverage.total === 0" class="text-muted-foreground flex flex-col items-center gap-2 py-6 text-sm">
        <ListTree class="size-6" />
        <span>{{ t('dashboard.coverage.noKnowledgePoints') }}</span>
        <NuxtLink to="/knowledge-points" class="text-primary hover:underline">{{ t('dashboard.coverage.manage') }}</NuxtLink>
      </div>
      <template v-else>
        <div class="grid gap-2">
          <div class="flex items-baseline justify-between text-sm">
            <span class="font-medium">{{ t('dashboard.coverage.rate') }}</span>
            <span class="text-muted-foreground text-xs">
              {{ t('dashboard.coverage.covered', { covered: formatNumber(coverage.covered), total: formatNumber(coverage.total) }) }}
            </span>
          </div>
          <div class="flex items-center gap-3">
            <Progress :model-value="coveragePercent" class="h-2" />
            <span class="w-10 text-right text-sm font-semibold tabular-nums">{{ coveragePercent }}%</span>
          </div>
        </div>

        <div class="grid gap-2">
          <h4 class="text-sm font-medium">{{ t('dashboard.coverage.topTitle') }}</h4>
          <p v-if="!coverage.top.length" class="text-muted-foreground text-sm">{{ t('dashboard.coverage.noLinked') }}</p>
          <ul v-else class="grid gap-1.5">
            <li v-for="kp in coverage.top" :key="kp.id" class="relative flex h-7 items-center rounded-md px-2 text-sm">
              <div
                class="bg-chart-2/20 absolute inset-y-0 left-0 rounded-md"
                :style="{ width: `${(kp.count / maxCount) * 100}%` }"
              />
              <span class="relative truncate pr-2" :title="kp.name">{{ kp.name }}</span>
              <span class="relative ml-auto font-medium tabular-nums">{{ formatNumber(kp.count) }}</span>
            </li>
          </ul>
        </div>

        <div v-if="uncoveredCount > 0" class="grid gap-2">
          <h4 class="flex items-center gap-1.5 text-sm font-medium">
            <CircleDashed class="text-muted-foreground size-4" />
            {{ t('dashboard.coverage.uncoveredTitle', { count: formatNumber(uncoveredCount) }) }}
          </h4>
          <div class="flex flex-wrap gap-1.5">
            <span
              v-for="kp in coverage.uncovered"
              :key="kp.id"
              class="bg-muted text-muted-foreground rounded-md px-2 py-0.5 text-xs"
            >{{ kp.name }}</span>
            <span v-if="uncoveredCount > coverage.uncovered.length" class="text-muted-foreground px-1 text-xs">…</span>
          </div>
        </div>
      </template>

      <div class="grid grid-cols-2 gap-3">
        <div class="rounded-lg border p-3">
          <div class="text-muted-foreground flex items-center gap-1.5 text-xs">
            <ListTree class="size-3.5" />{{ t('dashboard.coverage.withoutKp') }}
          </div>
          <div class="mt-1 text-xl font-semibold tabular-nums">{{ formatNumber(coverage.questions_without_kp) }}</div>
        </div>
        <div class="rounded-lg border p-3">
          <div class="text-muted-foreground flex items-center gap-1.5 text-xs">
            <Hash class="size-3.5" />{{ t('dashboard.coverage.withoutTag') }}
          </div>
          <div class="mt-1 text-xl font-semibold tabular-nums">{{ formatNumber(coverage.questions_without_tag) }}</div>
        </div>
      </div>
    </CardContent>
  </Card>
</template>
