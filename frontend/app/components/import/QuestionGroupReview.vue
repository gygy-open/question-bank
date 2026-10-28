<script setup lang="ts">
import { FileText } from '@lucide/vue'
import QuestionListItem from '@/components/QuestionListItem.vue'
import ImportDuplicateNotice from '@/components/dedup/ImportDuplicateNotice.vue'
import type { DuplicateCandidate, IntraBatchDuplicate } from '@/lib/questionDedup'
import RichContent from '@/components/rich-editor/RichContent.vue'
import { Badge } from '@/components/ui/badge'
import type { ImportReviewEntry } from '@/lib/importReview'
import type { KnowledgePoint, RichDoc } from '@/types'

defineProps<{
  entry: Extract<ImportReviewEntry, { kind: 'question_group' }>
  allKnowledgePoints?: KnowledgePoint[]
  duplicates?: Record<string, DuplicateCandidate[]>
  batchDuplicates?: Record<string, IntraBatchDuplicate[]>
  numberOf?: (ref: string) => number | undefined
}>()

const emit = defineEmits<{
  (event: 'edit', uid: string): void
}>()

const { t } = useI18n()
</script>

<template>
  <section class="overflow-hidden rounded-lg border bg-background">
    <div class="border-b bg-muted/30 px-4 py-4">
      <div class="mb-3 flex items-center gap-2">
        <FileText class="size-4 text-primary" />
        <h3 class="text-sm font-medium">{{ t('importReview.group.stimulus') }}</h3>
        <Badge variant="secondary">{{ t('importReview.group.memberCount', { count: entry.members.length }) }}</Badge>
      </div>
      <RichContent
        :content="entry.stimulus?.content as RichDoc | null"
        :empty-text="t('importReview.group.invalidStimulus')"
        class="text-sm"
      />
    </div>

    <div class="space-y-3 p-4">
      <template v-for="(member, memberIndex) in entry.members" :key="member.question.uid">
        <ImportDuplicateNotice
          v-if="member.question.temp_id"
          :candidates="duplicates?.[member.question.temp_id]"
          :batch="batchDuplicates?.[member.question.temp_id]"
          :number-of="numberOf"
        />
        <QuestionListItem
          :item="member.question"
          :index="memberIndex"
          :all-knowledge-points="allKnowledgePoints"
          hide-delete
          hide-duplicate
          @edit="emit('edit', member.question.uid)"
        />
      </template>
    </div>
  </section>
</template>