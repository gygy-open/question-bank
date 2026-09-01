<script setup lang="ts">
// 作答空间 NodeView：按行数渲染留白/横线，选中或悬停时显示行数与样式控件。
import { computed } from 'vue'
import { NodeViewWrapper } from '@tiptap/vue-3'
import { Minus, Plus, Baseline, Square } from '@lucide/vue'
import { ANSWER_SPACE_MAX_LINES, ANSWER_SPACE_MIN_LINES } from './AnswerSpace'

// 单行占高（rem）；与导出端 latex/docx 的每行 baselineskip 视觉相近。
const LINE_HEIGHT_REM = 1.75

const props = defineProps<{
  node: { attrs: { lines: number; style: 'blank' | 'lined' } }
  selected?: boolean
  updateAttributes: (attrs: Partial<{ lines: number; style: 'blank' | 'lined' }>) => void
}>()

const lines = computed(() => {
  const n = Number(props.node.attrs.lines)
  return Number.isFinite(n) && n >= 1 ? Math.round(n) : 3
})
const style = computed<'blank' | 'lined'>(() => (props.node.attrs.style === 'lined' ? 'lined' : 'blank'))
const heightRem = computed(() => `${lines.value * LINE_HEIGHT_REM}rem`)

function setLines(next: number) {
  props.updateAttributes({ lines: Math.min(ANSWER_SPACE_MAX_LINES, Math.max(ANSWER_SPACE_MIN_LINES, next)) })
}
function toggleStyle() {
  props.updateAttributes({ style: style.value === 'lined' ? 'blank' : 'lined' })
}
</script>

<template>
  <NodeViewWrapper
    data-composition-block
    class="composition-answer-space group relative my-1"
    :class="selected ? 'ring-2 ring-primary rounded-md' : ''"
    contenteditable="false"
  >
    <!-- 留白/横线本体 -->
    <div
      v-if="style === 'lined'"
      class="flex flex-col justify-between"
      :style="{ height: heightRem }"
      aria-label="作答横线"
    >
      <div
        v-for="i in lines"
        :key="i"
        class="border-b border-muted-foreground/40"
        :style="{ height: `${LINE_HEIGHT_REM}rem` }"
      />
    </div>
    <div
      v-else
      class="rounded-sm border border-dashed border-muted-foreground/20 bg-muted/10"
      :style="{ height: heightRem }"
      aria-label="作答留白"
    />

    <!-- 控件：选中或悬停时出现 -->
    <div
      class="absolute right-1 top-1 flex items-center gap-0.5 rounded-md border bg-background/95 px-1 py-0.5 shadow-sm opacity-0 transition-opacity group-hover:opacity-100"
      :class="selected ? 'opacity-100' : ''"
    >
      <button
        type="button" class="rounded p-1 hover:bg-muted disabled:opacity-40"
        :disabled="lines <= ANSWER_SPACE_MIN_LINES" title="减少行数"
        @mousedown.prevent @click="setLines(lines - 1)"
      >
        <Minus class="size-3.5" />
      </button>
      <span class="min-w-8 text-center text-xs tabular-nums text-muted-foreground">{{ lines }} 行</span>
      <button
        type="button" class="rounded p-1 hover:bg-muted disabled:opacity-40"
        :disabled="lines >= ANSWER_SPACE_MAX_LINES" title="增加行数"
        @mousedown.prevent @click="setLines(lines + 1)"
      >
        <Plus class="size-3.5" />
      </button>
      <span class="mx-0.5 h-4 w-px bg-border" />
      <button
        type="button" class="rounded p-1 hover:bg-muted"
        :title="style === 'lined' ? '切换为空白' : '切换为横线'"
        @mousedown.prevent @click="toggleStyle"
      >
        <Baseline v-if="style === 'lined'" class="size-3.5" />
        <Square v-else class="size-3.5" />
      </button>
    </div>
  </NodeViewWrapper>
</template>
