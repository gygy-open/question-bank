<script setup lang="ts">
import { Trophy } from '@lucide/vue'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { formatNumber } from '@/lib/locale'
import type { DashboardContributor, DashboardContributors } from '~/types/dashboard'

const props = defineProps<{ subjectId: number; refreshKey?: number }>()
const { t } = useI18n()
const { $api } = useNuxtApp()

const days = ref('30')
const items = ref<DashboardContributor[]>([])
const loading = ref(false)
let seq = 0

const load = async () => {
  const id = ++seq
  loading.value = true
  try {
    const res = await $api<DashboardContributors>('/dashboard/contributors', {
      query: { subject_id: props.subjectId, days: Number(days.value) },
    })
    if (id === seq) items.value = res.items
  } catch {
    if (id === seq) items.value = []
  } finally {
    if (id === seq) loading.value = false
  }
}

watch(() => [props.subjectId, days.value, props.refreshKey], load, { immediate: true })

const maxScore = computed(() => Math.max(1, ...items.value.map(c => c.created + c.reviewed)))
const displayName = (c: DashboardContributor) => c.full_name || c.username
const rankClass = (i: number) =>
  ['bg-amber-400/20 text-amber-700 dark:text-amber-300', 'bg-slate-400/20 text-slate-700 dark:text-slate-300', 'bg-orange-400/20 text-orange-700 dark:text-orange-300'][i]
  ?? 'bg-muted text-muted-foreground'
</script>

<template>
  <Card class="gap-4">
    <CardHeader class="flex flex-row items-start justify-between gap-4">
      <div class="grid gap-1.5">
        <CardTitle>{{ t('dashboard.contributors.title') }}</CardTitle>
        <CardDescription>{{ t('dashboard.contributors.description') }}</CardDescription>
      </div>
      <Tabs v-model="days">
        <TabsList>
          <TabsTrigger value="7">{{ t('dashboard.contributors.days', { days: 7 }) }}</TabsTrigger>
          <TabsTrigger value="30">{{ t('dashboard.contributors.days', { days: 30 }) }}</TabsTrigger>
          <TabsTrigger value="90">{{ t('dashboard.contributors.days', { days: 90 }) }}</TabsTrigger>
        </TabsList>
      </Tabs>
    </CardHeader>
    <CardContent>
      <div v-if="loading && !items.length" class="grid gap-3">
        <Skeleton v-for="i in 4" :key="i" class="h-10 w-full" />
      </div>
      <div v-else-if="!items.length" class="text-muted-foreground flex flex-col items-center gap-2 py-8 text-sm">
        <Trophy class="size-6" />
        {{ t('dashboard.contributors.empty') }}
      </div>
      <ul v-else class="grid gap-3" :class="loading ? 'opacity-60' : ''">
        <li v-for="(c, i) in items" :key="c.user_id" class="flex items-center gap-3">
          <span class="flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold" :class="rankClass(i)">
            {{ i + 1 }}
          </span>
          <Avatar class="size-8">
            <AvatarImage :src="c.avatar_url || ''" :alt="c.username" />
            <AvatarFallback class="text-xs">{{ displayName(c).slice(0, 2).toUpperCase() }}</AvatarFallback>
          </Avatar>
          <div class="grid min-w-0 flex-1 gap-1">
            <div class="flex items-baseline gap-2 text-sm">
              <span class="truncate font-medium">{{ displayName(c) }}</span>
              <span class="text-muted-foreground ml-auto shrink-0 text-xs tabular-nums">
                {{ t('dashboard.contributors.created', { count: formatNumber(c.created) }) }}
                ·
                {{ t('dashboard.contributors.reviewed', { count: formatNumber(c.reviewed) }) }}
              </span>
            </div>
            <div class="bg-muted flex h-1.5 overflow-hidden rounded-full">
              <div class="bg-chart-1 h-full" :style="{ width: `${(c.created / maxScore) * 100}%` }" />
              <div class="bg-chart-2 h-full" :style="{ width: `${(c.reviewed / maxScore) * 100}%` }" />
            </div>
          </div>
        </li>
      </ul>
    </CardContent>
  </Card>
</template>
