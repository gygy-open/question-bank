<script setup lang="ts">
import { computed, inject } from 'vue'
import { NodeViewWrapper } from '@tiptap/vue-3'
import { Files, Plus, Trash2 } from '@lucide/vue'
import RichContent from '@/components/rich-editor/RichContent.vue'
import RichEditor from '@/components/rich-editor/RichEditor.vue'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import QuestionBlockView from './QuestionBlockView.vue'
import { createAnswerSpaceNode, createRichTextNode, generateNodeId } from '@/lib/compositionDocument'
import type { EditorNode } from '@/lib/compositionDocument'
import { clampAnswerSpaceLines, resolveAnswerSpacePropsOrFallback } from '@/lib/answerSpaceRules'
import { ANSWER_SPACE_RULES_KEY, FALLBACK_ANSWER_SPACE_RULES } from '../editorContext'
import type { RichDoc, RichDocNode } from '@/types'

const props = defineProps<{
  node: { attrs: Record<string, unknown> }
  updateAttributes: (attrs: Record<string, unknown>) => void
  deleteNode: () => void
  selected?: boolean
}>()

const answerSpaceRules = inject(ANSWER_SPACE_RULES_KEY, FALLBACK_ANSWER_SPACE_RULES)

const children = computed(() => (props.node.attrs.children as EditorNode[] | null) ?? [])
const stimulus = computed(() => (props.node.attrs.stimulus as RichDocNode | null) ?? null)

function replaceChild(index: number, child: EditorNode) {
  const next = children.value.slice()
  next[index] = child
  props.updateAttributes({ children: next })
}

function removeChild(index: number) {
  props.updateAttributes({ children: children.value.filter((_, childIndex) => childIndex !== index) })
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
  const derived = resolveAnswerSpacePropsOrFallback(
    question.questionContent?.q_type,
    (question.props as { score?: number } | null)?.score,
    answerSpaceRules.value,
  )
  const answerSpace = createAnswerSpaceNode(derived.lines, derived.style)
  answerSpace.id = generateNodeId()
  answerSpace.sourceQuestionNodeId = question.id
  const next = children.value.slice()
  next.splice(afterIndex + 1, 0, answerSpace)
  props.updateAttributes({ children: next })
}

/** 拖拽底边调整作答区高度：每 LINE_PX 像素折算一行，与画布行高近似。 */
const LINE_PX = 28
function startResize(event: PointerEvent, index: number) {
  const child = children.value[index]
  if (!child) return
  const startY = event.clientY
  const startLines = ((child.props as { lines?: number } | null)?.lines) ?? 3
  const target = event.currentTarget as HTMLElement
  target.setPointerCapture(event.pointerId)

  const onMove = (move: PointerEvent) => {
    const delta = Math.round((move.clientY - startY) / LINE_PX)
    const lines = clampAnswerSpaceLines(startLines + delta)
    if (lines !== ((children.value[index]?.props as { lines?: number } | null)?.lines)) {
      patchAnswerSpace(index, { lines })
    }
  }
  const onUp = () => {
    target.releasePointerCapture(event.pointerId)
    target.removeEventListener('pointermove', onMove)
    target.removeEventListener('pointerup', onUp)
  }
  target.addEventListener('pointermove', onMove)
  target.addEventListener('pointerup', onUp)
}

/** 锚定到其后的小题：该小题被移出题组时，说明文字顺延到下一道题而非被丢弃。 */
function insertCustomBefore(index: number, anchorId: string | null) {
  const custom = createRichTextNode()
  custom.anchorBeforeNodeId = anchorId
  const next = children.value.slice()
  next.splice(index, 0, custom)
  props.updateAttributes({ children: next })
}

function patchCustomContent(index: number, content: RichDoc) {
  const child = children.value[index]!
  replaceChild(index, { ...child, content: content ?? null })
}

function patchAnswerSpace(index: number, patch: { lines?: number; style?: 'blank' | 'lined' }) {
  const child = children.value[index]!
  const lines = patch.lines == null ? undefined : Math.min(50, Math.max(1, patch.lines))
  replaceChild(index, {
    ...child,
    props: { ...(child.props as object), ...patch, ...(lines == null ? {} : { lines }) },
  })
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
          <div class="flex justify-center">
            <Button
              variant="ghost"
              size="sm"
              class="h-6 text-xs text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 focus:opacity-100"
              @click="insertCustomBefore(index, child.id)"
            >
              <Plus class="mr-1 size-3.5" />说明文字
            </Button>
          </div>
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
        <div
          v-else-if="child.nodeType === 'rich_text' || child.nodeType === 'heading'"
          class="flex items-start gap-2"
          @mousedown.stop
          @keydown.stop
        >
          <RichEditor
            class="min-w-0 flex-1"
            :model-value="child.content"
            placeholder="例如：阅读下面的文字，完成 1～5 题。"
            @update:model-value="patchCustomContent(index, $event)"
          />
          <Button variant="ghost" size="icon" class="size-7 shrink-0" title="删除说明文字" aria-label="删除说明文字" @click="removeChild(index)">
            <Trash2 class="size-3.5" />
          </Button>
        </div>
        <div v-else-if="child.nodeType === 'answer_space'" class="ml-3 border-l pl-3">
          <div class="flex items-center gap-2">
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
            <Button variant="ghost" size="icon" class="size-7" title="删除作答区" aria-label="删除作答区" @click="removeChild(index)">
              <Trash2 class="size-3.5" />
            </Button>
          </div>
          <!-- 所见即所得的高度预览；底边可拖拽调整行数 -->
          <div
            class="relative mt-1 rounded-sm bg-background/60"
            :style="{ height: `${((child.props as any)?.lines ?? 3) * 28}px` }"
          >
            <div
              v-if="(child.props as any)?.style === 'lined'"
              class="absolute inset-0"
              :style="{
                backgroundImage: 'repeating-linear-gradient(to bottom, transparent 0, transparent 27px, var(--color-border) 27px, var(--color-border) 28px)',
              }"
            />
            <div
              class="absolute inset-x-0 -bottom-1 h-2 cursor-ns-resize"
              role="separator"
              aria-label="拖拽调整作答区高度"
              @pointerdown.prevent.stop="startResize($event, index)"
            >
              <div class="mx-auto h-1 w-10 rounded-full bg-border opacity-0 transition-opacity group-hover:opacity-100" />
            </div>
          </div>
        </div>
      </template>
      <div class="flex justify-center">
        <Button
          variant="ghost"
          size="sm"
          class="h-6 text-xs text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 focus:opacity-100"
          @click="insertCustomBefore(children.length, null)"
        >
          <Plus class="mr-1 size-3.5" />说明文字
        </Button>
      </div>
    </div>
  </NodeViewWrapper>
</template>