<script setup lang="ts">
import { BookOpen, RefreshCw, Sparkles } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Skeleton } from '@/components/ui/skeleton'
import PageHeader from '~/components/PageHeader.vue'
import StatCards from '~/components/dashboard/StatCards.vue'
import TrendChart from '~/components/dashboard/TrendChart.vue'
import TypeDonut from '~/components/dashboard/TypeDonut.vue'
import QualityCard from '~/components/dashboard/QualityCard.vue'
import KnowledgeCoverage from '~/components/dashboard/KnowledgeCoverage.vue'
import ContributorBoard from '~/components/dashboard/ContributorBoard.vue'
import type { DashboardStats } from '~/types/dashboard'

const { t } = useI18n()
const { $api } = useNuxtApp()
const { currentSubjectId, currentSubject } = useSubjectContext()

const stats = ref<DashboardStats | null>(null)
const loading = ref(false)
const error = ref(false)
const refreshKey = ref(0)
let seq = 0

const load = async () => {
  const subjectId = currentSubjectId.value
  if (subjectId == null) {
    stats.value = null
    return
  }
  const id = ++seq
  loading.value = true
  error.value = false
  try {
    const res = await $api<DashboardStats>('/dashboard/stats', { query: { subject_id: subjectId } })
    if (id === seq) stats.value = res
  } catch {
    if (id === seq) error.value = true
  } finally {
    if (id === seq) loading.value = false
  }
}

const refresh = () => {
  refreshKey.value++
  load()
}

watch(currentSubjectId, () => {
  stats.value = null
  load()
}, { immediate: true })

// 页面被 keepalive 缓存:切回来时静默刷新,保证数字不过期。
let firstActivation = true
onActivated(() => {
  if (firstActivation) {
    firstActivation = false
    return
  }
  refresh()
})

const isEmpty = computed(() => stats.value?.overview.total_questions === 0)
</script>

<template>
  <PageHeader :title="t('nav.dashboard')">
    <template #actions>
      <span v-if="currentSubject" class="text-muted-foreground hidden text-sm sm:inline">{{ currentSubject.name }}</span>
      <Button variant="ghost" size="icon" :disabled="loading" :title="t('dashboard.refresh')" @click="refresh">
        <RefreshCw class="size-4" :class="loading ? 'animate-spin' : ''" />
      </Button>
    </template>
  </PageHeader>

  <div class="mx-auto grid w-full max-w-7xl gap-6 p-6">
    <Empty v-if="currentSubjectId == null" class="border">
      <EmptyHeader>
        <EmptyTitle>{{ t('dashboard.noSubject') }}</EmptyTitle>
      </EmptyHeader>
    </Empty>

    <Empty v-else-if="error && !stats" class="border">
      <EmptyHeader>
        <EmptyTitle>{{ t('dashboard.loadFailed') }}</EmptyTitle>
      </EmptyHeader>
      <EmptyContent>
        <Button variant="outline" @click="refresh">{{ t('dashboard.retry') }}</Button>
      </EmptyContent>
    </Empty>

    <template v-else-if="!stats">
      <div class="grid gap-4 sm:grid-cols-3">
        <Skeleton v-for="i in 3" :key="i" class="h-32 rounded-xl" />
      </div>
      <div class="grid gap-4 lg:grid-cols-3">
        <Skeleton class="h-80 rounded-xl lg:col-span-2" />
        <Skeleton class="h-80 rounded-xl" />
      </div>
    </template>

    <template v-else>
      <StatCards :overview="stats.overview" />

      <Empty v-if="isEmpty" class="border">
        <EmptyHeader>
          <EmptyMedia variant="icon"><BookOpen /></EmptyMedia>
          <EmptyTitle>{{ t('dashboard.empty.title') }}</EmptyTitle>
          <EmptyDescription>{{ t('dashboard.empty.description') }}</EmptyDescription>
        </EmptyHeader>
        <EmptyContent class="flex-row justify-center gap-2">
          <Button as-child>
            <NuxtLink to="/import/smart"><Sparkles class="size-4" />{{ t('nav.smartImport') }}</NuxtLink>
          </Button>
          <Button variant="outline" as-child>
            <NuxtLink to="/questions">{{ t('nav.questionBank') }}</NuxtLink>
          </Button>
        </EmptyContent>
      </Empty>

      <template v-else>
        <div class="grid gap-4 lg:grid-cols-3">
          <TrendChart class="lg:col-span-2" :trend="stats.trend" />
          <TypeDonut :items="stats.distribution.q_type" :total="stats.overview.total_questions" />
        </div>
        <div class="grid gap-4 lg:grid-cols-2">
          <QualityCard :distribution="stats.distribution" :total="stats.overview.total_questions" />
          <KnowledgeCoverage :coverage="stats.knowledge_coverage" />
        </div>
      </template>

      <ContributorBoard :subject-id="stats.subject_id" :refresh-key="refreshKey" />
    </template>
  </div>
</template>
