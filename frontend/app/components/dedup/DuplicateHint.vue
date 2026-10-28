<script setup lang="ts">
import { ChevronDown, CopyCheck } from '@lucide/vue'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import DuplicateCandidateList from '@/components/dedup/DuplicateCandidateList.vue'
import type { DuplicateCandidate } from '@/lib/questionDedup'

const props = defineProps<{ candidates: DuplicateCandidate[] }>()

const { t } = useI18n()
const expanded = ref(false)

const duplicates = computed(() => props.candidates.filter(c => c.level === 'duplicate').length)
const similar = computed(() => props.candidates.length - duplicates.value)
</script>

<template>
  <Alert v-if="candidates.length" class="border-amber-500/50 bg-amber-500/5">
    <CopyCheck class="size-4 text-amber-600" />
    <AlertTitle>{{ t('questionDedup.hint.title') }}</AlertTitle>
    <AlertDescription>
      <Collapsible v-model:open="expanded" class="w-full">
        <div class="flex flex-wrap items-center gap-x-3">
          <span>{{ t('questionDedup.hint.summary', { duplicates, similar }) }}</span>
          <CollapsibleTrigger class="inline-flex items-center gap-1 text-primary hover:underline">
            {{ expanded ? t('questionDedup.hint.collapse') : t('questionDedup.hint.expand') }}
            <ChevronDown class="size-3 transition-transform" :class="expanded && 'rotate-180'" />
          </CollapsibleTrigger>
        </div>
        <CollapsibleContent class="mt-2">
          <DuplicateCandidateList :candidates="candidates" />
        </CollapsibleContent>
      </Collapsible>
    </AlertDescription>
  </Alert>
</template>
