<script setup lang="ts">
// 组稿版本 snapshot v2 只读渲染：仅消费不可变快照，绝不查询当前题库，绝不提供编辑入口。
// module（question_details）在顶层只渲染一次，其 answer_item 子节点按有效字段渲染，
// 避免子节点在顶层被重复遍历。
import { computed } from 'vue'
import RichContent from '@/components/rich-editor/RichContent.vue'
import AnswerDisplay from '@/components/AnswerDisplay.vue'
import { Badge } from '@/components/ui/badge'
import { FileQuestion, ListChecks, AlertTriangle } from '@lucide/vue'
import { questionTypeLabel } from '@/lib/answerFormat'
import {
  buildSnapshotTree, effectiveAnswerFields, snapshotQuestionNodeMap,
} from '@/lib/compositionSnapshot'
import type { SnapshotTreeNode } from '@/lib/compositionSnapshot'
import { ANSWER_FIELD_KEYS } from '@/types/composition'
import type {
  AnswerFieldKey, CompositionSnapshotV2, SnapshotAnswerItemNode, SnapshotQuestionDetailsNode,
} from '@/types/composition'

const props = defineProps<{
  snapshot: CompositionSnapshotV2
}>()

const tree = computed(() => buildSnapshotTree(props.snapshot))
const questionNodeMap = computed(() => snapshotQuestionNodeMap(props.snapshot))

const FIELD_LABELS: Record<AnswerFieldKey, string> = {
  answer: '答案',
  thinking: '思路',
  analysis: '解析',
  summary: '小结',
}

const HEADING_CLASS: Record<number, string> = {
  1: 'text-2xl font-bold',
  2: 'text-xl font-semibold',
  3: 'text-lg font-semibold',
  4: 'text-base font-medium',
}

function headingClass(level: number): string {
  return HEADING_CLASS[level] ?? HEADING_CLASS[2]!
}

function moduleFieldsVisible(
  moduleNode: SnapshotTreeNode,
  child: SnapshotAnswerItemNode,
): Record<AnswerFieldKey, boolean> {
  return effectiveAnswerFields(moduleNode as unknown as SnapshotQuestionDetailsNode, child)
}

function sourceQuestion(child: SnapshotAnswerItemNode) {
  return questionNodeMap.value.get(child.source_question_node_id)?.question ?? null
}

function anyVisible(moduleNode: SnapshotTreeNode, child: SnapshotAnswerItemNode): boolean {
  const fields = moduleFieldsVisible(moduleNode, child)
  return ANSWER_FIELD_KEYS.some((k) => fields[k])
}
</script>

<template>
  <div class="space-y-6">
    <template v-for="node in tree" :key="node.id">
      <!-- 文本 -->
      <RichContent v-if="node.node_type === 'rich_text'" :content="node.content" />

      <!-- 标题 -->
      <div v-else-if="node.node_type === 'heading'" :class="headingClass(node.props.level)">
        <RichContent :content="node.content" class="[&_.prose]:my-0" />
      </div>

      <!-- 题目 -->
      <div v-else-if="node.node_type === 'question'" class="rounded-lg border bg-card p-4">
        <div class="space-y-3">
          <div class="flex items-center gap-2">
            <FileQuestion class="h-3.5 w-3.5 text-muted-foreground" />
            <Badge variant="secondary" class="text-xs">{{ questionTypeLabel(node.question.q_type) }}</Badge>
            <span class="text-xs text-muted-foreground">#{{ node.question.id }} · 版本 r{{ node.question_revision }}</span>
          </div>
          <RichContent :content="node.question.content" empty-text="（无题干）" />
          <ul v-if="node.question.options?.length" class="space-y-1">
            <li v-for="opt in node.question.options" :key="opt.id" class="flex gap-2 text-sm">
              <span class="font-medium text-muted-foreground">{{ opt.label }}.</span>
              <RichContent :content="opt.content" class="[&_.prose]:my-0" />
            </li>
          </ul>
        </div>
      </div>

      <!-- 分页 -->
      <div v-else-if="node.node_type === 'page_break'" class="flex items-center gap-3 py-2">
        <div class="h-px flex-1 border-t-2 border-dashed border-muted-foreground/40" />
        <span class="text-xs font-medium text-muted-foreground">分页</span>
        <div class="h-px flex-1 border-t-2 border-dashed border-muted-foreground/40" />
      </div>

      <!-- 答案汇总模块：按 module 子节点顺序渲染（自定义节点 + answer_item） -->
      <div v-else-if="node.node_type === 'question_details'" class="rounded-lg border bg-muted/30 p-4">
        <div class="mb-3 flex items-center gap-2">
          <ListChecks class="h-3.5 w-3.5 text-muted-foreground" />
          <span class="text-sm font-medium">
            {{ node.props.scope === 'before' ? '答案汇总（此前题目）' : '答案汇总（全篇）' }}
          </span>
        </div>

        <p v-if="node.children.length === 0" class="text-xs text-muted-foreground">无可汇总的题目</p>

        <div v-else class="space-y-4">
          <template v-for="child in node.children" :key="child.id">
            <!-- 自定义标题 -->
            <div v-if="child.node_type === 'heading'" :class="headingClass(child.props.level)">
              <RichContent :content="child.content" class="[&_.prose]:my-0" />
            </div>

            <!-- 自定义文本 -->
            <RichContent v-else-if="child.node_type === 'rich_text'" :content="child.content" />

            <!-- answer_item：按有效字段渲染真实冻结内容 -->
            <div v-else-if="child.node_type === 'answer_item'">
              <div v-if="!sourceQuestion(child)" class="flex items-center gap-2 text-xs text-muted-foreground">
                <AlertTriangle class="h-3.5 w-3.5" /> 题目内容在定稿时不可用
              </div>
              <div v-else-if="anyVisible(node, child)" class="flex gap-2 text-sm">
                <FileQuestion class="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                <div class="min-w-0 flex-1 space-y-2">
                  <span class="text-xs text-muted-foreground">#{{ sourceQuestion(child)!.id }}</span>
                  <template v-for="key in ANSWER_FIELD_KEYS" :key="key">
                    <div v-if="moduleFieldsVisible(node, child)[key]" class="flex flex-col gap-0.5">
                      <span class="text-xs font-medium text-muted-foreground">{{ FIELD_LABELS[key] }}</span>
                      <AnswerDisplay
                        v-if="key === 'answer'"
                        :answer="sourceQuestion(child)!.answer"
                        :options="sourceQuestion(child)!.options"
                      />
                      <RichContent v-else :content="sourceQuestion(child)![key]" class="[&_.prose]:my-0" empty-text="（空）" />
                    </div>
                  </template>
                </div>
              </div>
            </div>
          </template>
        </div>
      </div>
    </template>
  </div>
</template>
