<script setup lang="ts">
import { ExternalLink } from '@lucide/vue'
import { Badge } from '@/components/ui/badge'
import { formatRelativeTime } from '@/lib/utils'
import { type DuplicateCandidate, similarityPercent } from '@/lib/questionDedup'

defineProps<{ candidates: DuplicateCandidate[] }>()

const { t, te } = useI18n()

const statusLabel = (status: string) => {
  const key = `questions.statuses.${status}`
  return te(key) ? t(key) : status
}
</script>

<template>
  <ul class="space-y-2">
    <li v-for="c in candidates" :key="c.question_id" class="rounded-md border p-3 text-sm">
      <div class="flex flex-wrap items-center gap-2">
        <Badge :variant="c.level === 'duplicate' ? 'destructive' : 'secondary'">
          {{ c.level === 'duplicate'
            ? t('questionDedup.level.duplicate')
            : t('questionDedup.level.similar', { percent: similarityPercent(c.similarity) }) }}
        </Badge>
        <Badge v-if="c.variant" variant="outline">{{ t('questionDedup.variant') }}</Badge>
        <span class="text-muted-foreground">#{{ c.question_id }} · {{ statusLabel(c.status) }}</span>
        <span v-if="c.created_by || c.created_at" class="text-muted-foreground">
          · {{ [c.created_by, c.created_at ? formatRelativeTime(c.created_at) : null].filter(Boolean).join(' · ') }}
        </span>
        <NuxtLink
          :to="{ path: '/questions', query: { id: c.question_id } }"
          target="_blank"
          class="ml-auto inline-flex items-center gap-1 text-primary hover:underline"
        >
          {{ t('questionDedup.view') }}<ExternalLink class="size-3" />
        </NuxtLink>
      </div>
      <p class="mt-2 line-clamp-3 break-all text-muted-foreground">{{ c.preview }}</p>
      <div v-if="c.diff.length" class="mt-2 space-y-1">
        <p class="text-xs font-medium">{{ t('questionDedup.differences') }}</p>
        <p v-for="(d, i) in c.diff" :key="i" class="break-all font-mono text-xs">
          <span class="text-muted-foreground">…{{ d.before }}</span>
          <del v-if="d.existing" class="bg-destructive/15 text-destructive">{{ d.existing }}</del>
          <ins v-if="d.incoming" class="bg-green-500/15 text-green-700 no-underline dark:text-green-400">{{ d.incoming }}</ins>
          <span class="text-muted-foreground">{{ d.after }}…</span>
        </p>
      </div>
    </li>
  </ul>
</template>
