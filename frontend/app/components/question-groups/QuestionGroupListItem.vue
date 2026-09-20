<script setup lang="ts">
import { FilePenLine, FilePlus2, Lock, ShoppingBasket, Trash2 } from '@lucide/vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import RichContent from '@/components/rich-editor/RichContent.vue'
import type { QuestionGroup } from '@/types'

defineProps<{
  group: QuestionGroup
  canEdit: boolean
}>()

defineEmits<{
  delete: [group: QuestionGroup]
  addBasket: [group: QuestionGroup]
  addComposition: [group: QuestionGroup]
}>()

const statusLabel: Record<string, string> = {
  draft: '草稿', pending: '待审核', published: '已发布', archived: '已归档',
}
const typeLabel: Record<string, string> = {
  single_choice: '单选题', multiple_choice: '多选题', true_false: '判断题',
  fill_in_the_blank: '填空题', free_response: '解答题',
}
</script>

<template>
  <article class="border-b py-5 last:border-b-0">
    <div class="flex items-start justify-between gap-3">
      <div class="flex min-w-0 flex-wrap items-center gap-2">
        <span class="font-mono text-xs text-muted-foreground">题组 #{{ group.id }}</span>
        <Badge variant="secondary">{{ statusLabel[group.status] || group.status }}</Badge>
        <Badge v-if="group.visibility === 'private'" variant="outline" class="gap-1"><Lock class="size-3" />私有</Badge>
        <Badge variant="outline">{{ group.items.length }} 道题</Badge>
        <span v-if="group.source" class="truncate text-xs text-muted-foreground">{{ group.source }}</span>
      </div>
      <div class="flex shrink-0 items-center gap-1">
        <Button variant="ghost" size="icon" title="全部加入试题篮" aria-label="全部加入试题篮" @click="$emit('addBasket', group)"><ShoppingBasket class="size-4" /></Button>
        <Button variant="ghost" size="icon" title="全部直接加入稿件" aria-label="全部直接加入稿件" @click="$emit('addComposition', group)"><FilePlus2 class="size-4" /></Button>
        <Button v-if="canEdit" as-child variant="ghost" size="icon" title="编辑题组" aria-label="编辑题组">
          <NuxtLink :to="`/question-groups/${group.id}/edit`"><FilePenLine class="size-4" /></NuxtLink>
        </Button>
        <Button v-if="canEdit" variant="ghost" size="icon" class="text-destructive" title="删除题组" aria-label="删除题组" @click="$emit('delete', group)"><Trash2 class="size-4" /></Button>
      </div>
    </div>

    <div class="mt-4 border-l-2 border-primary/40 pl-4">
      <div class="mb-1 text-xs font-medium text-muted-foreground">题目材料</div>
      <RichContent :content="group.stimulus.content" empty-text="（空题目材料）" class="line-clamp-4 text-sm" />
    </div>

    <ol class="mt-4 divide-y border-y">
      <li v-for="item in [...group.items].sort((a, b) => a.position - b.position)" :key="item.question_id" class="flex gap-3 py-3 text-sm">
        <span class="w-6 shrink-0 text-right font-medium text-muted-foreground">{{ item.position + 1 }}.</span>
        <div class="min-w-0 flex-1">
          <div class="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
            <span>#{{ item.question_id }}</span><span>{{ typeLabel[item.question.q_type] || item.question.q_type }}</span><span>难度 {{ item.question.difficulty }}</span>
          </div>
          <RichContent :content="item.question.content" empty-text="（空题目）" class="line-clamp-2 text-sm" />
        </div>
      </li>
    </ol>
  </article>
</template>