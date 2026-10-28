<script setup lang="ts">
import { ChevronDown, CopyCheck } from '@lucide/vue'
import { Badge } from '@/components/ui/badge'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import DuplicateCandidateList from '@/components/dedup/DuplicateCandidateList.vue'
import {
  type DuplicateCandidate,
  type IntraBatchDuplicate,
  similarityPercent,
  strongestLevel,
} from '@/lib/questionDedup'

const props = defineProps<{
  candidates?: DuplicateCandidate[]
  batch?: IntraBatchDuplicate[]
  /** 本批题目 temp_id → 题号(从 1 开始) */
  numberOf?: (ref: string) => number | undefined
}>()

const { t } = useI18n()
const expanded = ref(false)

const existing = computed(() => props.candidates ?? [])
const twins = computed(() => props.batch ?? [])
const level = computed(() => {
  const own = strongestLevel(existing.value)
  if (own === 'duplicate' || twins.value.some(b => b.level === 'duplicate')) return 'duplicate'
  return own ?? (twins.value.length ? 'similar' : null)
})

const twinLabel = (b: IntraBatchDuplicate) => {
  const n = props.numberOf?.(b.ref)
  const target = n ? t('questionDedup.import.batchQuestion', { number: n }) : b.ref
  return b.level === 'duplicate'
    ? t('questionDedup.import.batchDuplicate', { target })
    : t('questionDedup.import.batchSimilar', { target, percent: similarityPercent(b.similarity) })
}
</script>

<template>
  <Collapsible v-if="level" v-model:open="expanded" class="rounded-md border border-amber-500/40 bg-amber-500/5 px-3 py-2 text-sm">
    <div class="flex flex-wrap items-center gap-2">
      <CopyCheck class="size-4 text-amber-600" />
      <Badge :variant="level === 'duplicate' ? 'destructive' : 'secondary'">
        {{ level === 'duplicate' ? t('questionDedup.level.duplicate') : t('questionDedup.import.similarShort') }}
      </Badge>
      <span v-if="existing.length">{{ t('questionDedup.import.existing', { count: existing.length }) }}</span>
      <span v-for="b in twins" :key="b.ref" class="text-muted-foreground">{{ twinLabel(b) }}</span>
      <CollapsibleTrigger v-if="existing.length" class="ml-auto inline-flex items-center gap-1 text-primary hover:underline">
        {{ expanded ? t('questionDedup.hint.collapse') : t('questionDedup.hint.expand') }}
        <ChevronDown class="size-3 transition-transform" :class="expanded && 'rotate-180'" />
      </CollapsibleTrigger>
    </div>
    <CollapsibleContent class="mt-2">
      <DuplicateCandidateList :candidates="existing" />
    </CollapsibleContent>
  </Collapsible>
</template>
