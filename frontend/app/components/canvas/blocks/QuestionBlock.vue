<script setup lang="ts">
import { computed, inject } from 'vue'
import { Input } from '@/components/ui/input'
import MarkdownPreview from '@/components/MarkdownPreview.vue'
import type { EditorBlock } from '../blockRegistry'
import { CanvasContextKey } from '../useCanvasContext'
import { FIELD_ORDER, FIELD_LABEL, resolveRegion, fieldValue } from '@/lib/displayPolicy'
import type { DisplayField } from '~/types'

const props = defineProps<{
  block: EditorBlock
  number?: string
}>()

const emit = defineEmits<{ change: [] }>()

const ctx = inject(CanvasContextKey, { documentDisplay: null })

const scoringEnabled = computed(() => ctx.documentScoring?.enabled !== false)

const q = computed(() => props.block.question)
const isChoice = computed(
  () => q.value?.q_type === 'single_choice' || q.value?.q_type === 'multiple_choice',
)
const options = computed(() => q.value?.options || [])

const blockDisplay = computed(() => props.block.content?.display)
const regionFor = (f: DisplayField) => resolveRegion(f, blockDisplay.value, ctx.documentDisplay)
const inlineFields = computed<DisplayField[]>(() =>
  q.value ? FIELD_ORDER.filter((f) => regionFor(f) === 'inline' && !!fieldValue(q.value!, f)) : [],
)
const appendixLabels = computed<string[]>(() =>
  q.value
    ? FIELD_ORDER.filter((f) => regionFor(f) === 'appendix' && !!fieldValue(q.value!, f)).map((f) => FIELD_LABEL[f])
    : [],
)

const score = computed({
  get: () => props.block.content.score ?? null,
  set: (v: number | null) => {
    if (v == null || Number.isNaN(v)) delete props.block.content.score
    else props.block.content.score = v
    emit('change')
  },
})
</script>

<template>
  <div class="group/q relative pl-8 pr-20 py-2 rounded-md hover:bg-muted/40 transition-colors">
    <!-- 分值: 题目自身的高频属性, 留在块内内联编辑; 查看/显示设置等低频操作收进手柄菜单 -->
    <div
      v-if="scoringEnabled"
      class="absolute right-2 top-1.5 flex items-center gap-1.5 opacity-0 group-hover/q:opacity-100 transition-opacity"
    >
      <Input
        v-model.number="score"
        type="number"
        min="0"
        step="0.5"
        placeholder="分值"
        class="h-7 w-16 text-xs"
      />
    </div>

    <div class="flex gap-2">
      <span v-if="number" class="font-medium text-foreground shrink-0">{{ number }}.</span>
      <div class="flex-1 min-w-0 leading-relaxed">
        <MarkdownPreview v-if="q" :content="q.content" />
        <span v-else class="text-muted-foreground italic">题目已删除</span>
        <span v-if="scoringEnabled && score != null" class="ml-2 text-xs text-muted-foreground">（{{ score }} 分）</span>
      </div>
    </div>

    <div v-if="isChoice && options.length > 0" class="mt-2 pl-6 space-y-1.5">
      <div v-for="opt in options" :key="opt.label" class="flex gap-2">
        <span class="font-medium text-foreground shrink-0">{{ opt.label }}.</span>
        <div class="flex-1 min-w-0 [&_.prose]:my-0 [&_.prose>p]:my-0">
          <MarkdownPreview :content="opt.content" />
        </div>
      </div>
    </div>

    <!-- 按有效显示策略: inline 字段内联预览; appendix 字段仅标记 -->
    <div v-if="q && inlineFields.length" class="mt-2 pl-6 space-y-1 text-sm">
      <div v-for="f in inlineFields" :key="f" :class="f === 'answer' ? 'text-foreground' : 'text-muted-foreground'">
        <span class="font-medium">【{{ FIELD_LABEL[f] }}】</span>
        <MarkdownPreview :content="String(fieldValue(q, f) || '')" class="inline [&_.prose]:my-0 [&_.prose>p]:my-0" />
      </div>
    </div>
    <div v-if="q && appendixLabels.length" class="mt-1 pl-6 text-xs italic text-muted-foreground">
      （{{ appendixLabels.join('、') }}见卷末）
    </div>
  </div>
</template>
