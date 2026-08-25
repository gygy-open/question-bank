<script setup lang="ts">
// 组稿版本只读渲染：仅消费不可变 snapshot，绝不查询当前题库，绝不提供编辑入口。
import { computed } from 'vue'
import RichContent from '@/components/rich-editor/RichContent.vue'
import AnswerDisplay from '@/components/AnswerDisplay.vue'
import { Badge } from '@/components/ui/badge'
import { FileQuestion, ListChecks, AlertTriangle } from '@lucide/vue'
import { questionTypeLabel } from '@/lib/answerFormat'
import { isEmptyRichDoc } from '@/components/rich-editor/richDoc'
import { snapshotQuestionMap, resolveSummaryQuestions } from '@/lib/compositionSnapshot'
import type {
  CompositionSnapshotV1,
  SnapshotAnswerSummaryBlock,
} from '@/types/composition'

const props = defineProps<{
  snapshot: CompositionSnapshotV1
}>()

// 全篇仅建一次映射，供 answer_summary 复用。
const questionMap = computed(() => snapshotQuestionMap(props.snapshot))

const HEADING_CLASS: Record<number, string> = {
  1: 'text-2xl font-bold',
  2: 'text-xl font-semibold',
  3: 'text-lg font-semibold',
  4: 'text-base font-medium',
}

function headingClass(level: number): string {
  return HEADING_CLASS[level] ?? HEADING_CLASS[2]!
}

function summaryQuestions(block: SnapshotAnswerSummaryBlock) {
  return resolveSummaryQuestions(props.snapshot, block, questionMap.value)
}
</script>

<template>
  <div class="space-y-6">
    <template v-for="(block, i) in snapshot.blocks" :key="i">
      <!-- 文本 -->
      <RichContent
        v-if="block.block_type === 'rich_text'"
        :content="block.content"
      />

      <!-- 标题 -->
      <div v-else-if="block.block_type === 'heading'" :class="headingClass(block.props.level)">
        <RichContent :content="block.content" class="[&_.prose]:my-0" />
      </div>

      <!-- 题目 -->
      <div
        v-else-if="block.block_type === 'question'"
        class="rounded-lg border bg-card p-4"
      >
        <div v-if="!block.question" class="flex items-center gap-2 py-2 text-sm text-muted-foreground">
          <AlertTriangle class="h-4 w-4" />
          题目内容在定稿时不可用（#{{ block.question_id }}）
        </div>
        <div v-else class="space-y-3">
          <div class="flex items-center gap-2">
            <FileQuestion class="h-3.5 w-3.5 text-muted-foreground" />
            <Badge variant="secondary" class="text-xs">{{ questionTypeLabel(block.question.q_type) }}</Badge>
            <span class="text-xs text-muted-foreground">#{{ block.question.id }} · 版本 r{{ block.question_revision }}</span>
          </div>
          <RichContent :content="block.question.content" empty-text="（无题干）" />
          <ul v-if="block.question.options?.length" class="space-y-1">
            <li v-for="opt in block.question.options" :key="opt.id" class="flex gap-2 text-sm">
              <span class="font-medium text-muted-foreground">{{ opt.label }}.</span>
              <RichContent :content="opt.content" class="[&_.prose]:my-0" />
            </li>
          </ul>
        </div>
      </div>

      <!-- 分页 -->
      <div v-else-if="block.block_type === 'page_break'" class="flex items-center gap-3 py-2">
        <div class="h-px flex-1 border-t-2 border-dashed border-muted-foreground/40" />
        <span class="text-xs font-medium text-muted-foreground">分页</span>
        <div class="h-px flex-1 border-t-2 border-dashed border-muted-foreground/40" />
      </div>

      <!-- 答案汇总（真实只读解析） -->
      <div
        v-else-if="block.block_type === 'answer_summary'"
        class="rounded-lg border bg-muted/30 p-4"
      >
        <div class="mb-3 flex items-center gap-2">
          <ListChecks class="h-3.5 w-3.5 text-muted-foreground" />
          <span class="text-sm font-medium">
            {{ block.props.mode === 'before' ? '答案与解析（此前题目）' : '答案与解析（全篇）' }}
          </span>
        </div>
        <p
          v-if="summaryQuestions(block).length === 0"
          class="text-xs text-muted-foreground"
        >
          无可汇总的题目
        </p>
        <ol v-else class="space-y-3">
          <li
            v-for="(q, qi) in summaryQuestions(block)"
            :key="`${i}-${q.id}`"
            class="flex gap-2 text-sm"
          >
            <span class="font-mono text-muted-foreground shrink-0">{{ qi + 1 }}.</span>
            <div class="min-w-0 flex-1 space-y-2">
              <div>
                <span class="mr-2 text-xs text-muted-foreground">答案</span>
                <AnswerDisplay :answer="q.answer" :options="q.options" class="inline" />
              </div>
              <div v-if="!isEmptyRichDoc(q.analysis)">
                <span class="text-xs text-muted-foreground">解析</span>
                <RichContent :content="q.analysis" class="[&_.prose]:my-0" />
              </div>
            </div>
          </li>
        </ol>
      </div>
    </template>

    <p v-if="!snapshot.blocks.length" class="py-8 text-center text-sm text-muted-foreground">
      此版本没有内容块
    </p>
  </div>
</template>
