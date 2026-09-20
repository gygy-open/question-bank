<script setup lang="ts">
import { FileText } from '@lucide/vue'
import QuestionListItem from '@/components/QuestionListItem.vue'
import RichContent from '@/components/rich-editor/RichContent.vue'
import { Badge } from '@/components/ui/badge'
import type { ImportReviewEntry } from '@/lib/importReview'
import type { KnowledgePoint, RichDoc } from '@/types'

defineProps<{
  entry: Extract<ImportReviewEntry, { kind: 'question_group' }>
  allKnowledgePoints?: KnowledgePoint[]
}>()

const emit = defineEmits<{
  (event: 'edit', uid: string): void
}>()
</script>

<template>
  <section class="overflow-hidden rounded-lg border bg-background">
    <div class="border-b bg-muted/30 px-4 py-4">
      <div class="mb-3 flex items-center gap-2">
        <FileText class="size-4 text-primary" />
        <h3 class="text-sm font-medium">题目材料</h3>
        <Badge variant="secondary">{{ entry.members.length }} 道小题</Badge>
      </div>
      <RichContent
        :content="entry.stimulus?.content as RichDoc | null"
        empty-text="（题目材料引用无效）"
        class="text-sm"
      />
    </div>

    <div class="space-y-3 p-4">
      <QuestionListItem
        v-for="(member, memberIndex) in entry.members"
        :key="member.question.uid"
        :item="member.question"
        :index="memberIndex"
        :all-knowledge-points="allKnowledgePoints"
        hide-delete
        hide-duplicate
        @edit="emit('edit', member.question.uid)"
      />
    </div>
  </section>
</template>