<script setup lang="ts">
import type { Component } from 'vue'
import { BookOpen, CircleCheck, Clock, FileText, Layers, ListTree, Tags } from '@lucide/vue'
import { formatNumber } from '@/lib/locale'
import type { DashboardOverview } from '~/types/dashboard'

const props = defineProps<{ overview: DashboardOverview }>()
const { t } = useI18n()
const NuxtLink = resolveComponent('NuxtLink')

interface StatCard {
  key: string
  label: string
  value: number
  hint?: string
  icon: Component
  to?: string
  tone?: string
}

const primary = computed<StatCard[]>(() => {
  const o = props.overview
  const ratio = o.total_questions ? Math.round((o.published / o.total_questions) * 100) : 0
  return [
    {
      key: 'total', label: t('dashboard.overview.totalQuestions'), value: o.total_questions,
      hint: t('dashboard.overview.newThisWeek', { count: formatNumber(o.new_questions_7d) }),
      icon: BookOpen, to: '/questions', tone: 'text-primary bg-primary/10',
    },
    {
      key: 'published', label: t('questions.statuses.published'), value: o.published,
      hint: t('dashboard.overview.publishedRatio', { percent: ratio }),
      icon: CircleCheck, tone: 'text-emerald-600 bg-emerald-500/10 dark:text-emerald-400',
    },
    {
      key: 'pending', label: t('questions.statuses.pending'), value: o.pending,
      hint: t('dashboard.overview.pendingHint'),
      icon: Clock, tone: 'text-amber-600 bg-amber-500/10 dark:text-amber-400',
    },
  ]
})

const secondary = computed<StatCard[]>(() => {
  const o = props.overview
  return [
    { key: 'stimuli', label: t('dashboard.overview.stimuli'), value: o.stimuli, icon: FileText, to: '/materials' },
    { key: 'compositions', label: t('dashboard.overview.compositions'), value: o.compositions, icon: Layers, to: '/compositions/shared' },
    { key: 'kps', label: t('nav.knowledgePoints'), value: o.knowledge_points, icon: ListTree, to: '/knowledge-points' },
    { key: 'tags', label: t('dashboard.overview.tags'), value: o.tags, icon: Tags, to: '/tags' },
  ]
})
</script>

<template>
  <div class="grid gap-4">
    <div class="grid gap-4 sm:grid-cols-3">
      <component
        :is="card.to ? NuxtLink : 'div'"
        v-for="card in primary"
        :key="card.key"
        :to="card.to"
        class="bg-card text-card-foreground flex flex-col gap-3 rounded-xl border p-5 shadow-sm transition-colors"
        :class="card.to ? 'hover:border-primary/40' : ''"
      >
        <div class="flex items-center justify-between">
          <span class="text-muted-foreground text-sm">{{ card.label }}</span>
          <span class="flex size-8 items-center justify-center rounded-lg" :class="card.tone">
            <component :is="card.icon" class="size-4" />
          </span>
        </div>
        <div class="text-3xl font-semibold tabular-nums tracking-tight">{{ formatNumber(card.value) }}</div>
        <div v-if="card.hint" class="text-muted-foreground text-xs">{{ card.hint }}</div>
      </component>
    </div>
    <div class="grid grid-cols-2 gap-4 xl:grid-cols-4">
      <NuxtLink
        v-for="card in secondary"
        :key="card.key"
        :to="card.to!"
        class="bg-card hover:bg-accent/50 flex items-center gap-3 rounded-lg border px-4 py-3 transition-colors"
      >
        <component :is="card.icon" class="text-muted-foreground size-4 shrink-0" />
        <span class="text-muted-foreground truncate text-sm">{{ card.label }}</span>
        <span class="ml-auto font-semibold tabular-nums">{{ formatNumber(card.value) }}</span>
      </NuxtLink>
    </div>
  </div>
</template>
