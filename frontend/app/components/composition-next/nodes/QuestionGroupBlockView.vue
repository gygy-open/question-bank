<script setup lang="ts">
import { computed } from 'vue'
import { NodeViewWrapper } from '@tiptap/vue-3'
import { Files, Plus, Trash2 } from '@lucide/vue'
import RichContent from '@/components/rich-editor/RichContent.vue'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import QuestionBlockView from './QuestionBlockView.vue'
import { createAnswerSpaceNode, generateNodeId } from '@/lib/compositionDocument'
import type { EditorNode } from '@/lib/compositionDocument'
import type { RichDocNode } from '@/types'

const props = defineProps<{
  node: { attrs: Record<string, unknown> }
  updateAttributes: (attrs: Record<string, unknown>) => void
  deleteNode: () => void
  selected?: boolean
}>()

const children = computed(() => (props.node.attrs.children as EditorNode[] | null) ?? [])
const stimulus = computed(() => (props.node.attrs.stimulus as RichDocNode | null) ?? null)

function replaceChild(index: number, child: EditorNode) {
  const next = children.value.slice()
  next[index] = child
  props.updateAttributes({ children: next })
}

function updateQuestion(index: number, attrs: Record<string, unknown>) {
  const child = children.value[index]!
  replaceChild(index, { ...child, props: (attrs.props as EditorNode['props']) ?? child.props })
}

function hasAnswerSpace(index: number) {
  const question = children.value[index]
  const next = children.value[index + 1]
  return question?.nodeType === 'question'
    && next?.nodeType === 'answer_space'
    && next.sourceQuestionNodeId === question.id
}

function addAnswerSpace(afterIndex: number) {
  const question = children.value[afterIndex]
  if (!question || question.nodeType !== 'question' || hasAnswerSpace(afterIndex)) return
  const answerSpace = createAnswerSpaceNode()
  answerSpace.id = generateNodeId()
  answerSpace.sourceQuestionNodeId = question.id
  const next = children.value.slice()
  next.splice(afterIndex + 1, 0, answerSpace)
  props.updateAttributes({ children: next })
}

function patchAnswerSpace(index: number, patch: { lines?: number; style?: 'blank' | 'lined' }) {
  const child = children.value[index]!
  const lines = patch.lines == null ? undefined : Math.min(50, Math.max(1, patch.lines))
  replaceChild(index, {
    ...child,
    props: { ...(child.props as object), ...patch, ...(lines == null ? {} : { lines }) },
  })
}

function removeAnswerSpace(index: number) {
  props.updateAttributes({ children: children.value.filter((_, childIndex) => childIndex !== index) })
}
</script>

<template>
  <NodeViewWrapper
    data-composition-block
    class="group relative -mx-3 my-3 border-y bg-muted/20 px-3 py-4"
    :class="selected ? 'border-primary/50' : 'border-border'"
    contenteditable="false"
  >
    <div class="mb-3 flex items-center gap-2">
      <Files class="size-4 text-muted-foreground" />
      <span class="text-sm font-medium">题组 #{{ node.attrs.questionGroupId }}</span>
      <Badge variant="secondary" class="text-[11px]">r{{ node.attrs.questionGroupRevision }}</Badge>
      <Button class="ml-auto size-7" variant="ghost" size="icon" title="删除整个题组" aria-label="删除整个题组" @click="deleteNode">
        <Trash2 class="size-4 text-destructive" />
      </Button>
    </div>

    <div class="mb-4 border-l-2 border-primary/30 pl-4">
      <RichContent :content="stimulus" empty-text="（无材料）" />
    </div>

    <div class="space-y-2">
      <template v-for="(child, index) in children" :key="child.id">
        <div v-if="child.nodeType === 'question'">
          <QuestionBlockView
            :node="{ attrs: { uid: child.id, questionId: child.questionId, questionRevision: child.questionRevision, snapshot: child.questionContent, props: child.props } }"
            :update-attributes="attrs => updateQuestion(index, attrs)"
            :delete-node="() => {}"
            :deletable="false"
            :syncable="false"
          />
          <Button
            v-if="!hasAnswerSpace(index)"
            variant="ghost"
            size="sm"
            class="ml-3 h-7 text-xs text-muted-foreground"
            @click="addAnswerSpace(index)"
          >
            <Plus class="mr-1 size-3.5" />作答区
          </Button>
        </div>
        <div v-else-if="child.nodeType === 'answer_space'" class="ml-3 flex items-center gap-2 border-l pl-3">
          <span class="text-xs text-muted-foreground">作答区</span>
          <input
            type="number" min="1" max="50"
            class="h-7 w-16 rounded border bg-background px-2 text-xs"
            :value="(child.props as any)?.lines ?? 3"
            @input="patchAnswerSpace(index, { lines: Number(($event.target as HTMLInputElement).value) || 1 })"
          >
          <select
            class="h-7 rounded border bg-background px-2 text-xs"
            :value="(child.props as any)?.style ?? 'blank'"
            @change="patchAnswerSpace(index, { style: ($event.target as HTMLSelectElement).value as 'blank' | 'lined' })"
          >
            <option value="blank">留白</option>
            <option value="lined">横线</option>
          </select>
          <Button variant="ghost" size="icon" class="size-7" title="删除作答区" aria-label="删除作答区" @click="removeAnswerSpace(index)">
            <Trash2 class="size-3.5" />
          </Button>
        </div>
      </template>
    </div>
  </NodeViewWrapper>
</template>