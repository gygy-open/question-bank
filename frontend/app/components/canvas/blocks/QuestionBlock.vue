<script setup lang="ts">
import { computed, inject } from 'vue'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Eye } from '@lucide/vue'
import MarkdownPreview from '@/components/MarkdownPreview.vue'
import QuestionDisplayOverride from './QuestionDisplayOverride.vue'
import type { EditorBlock } from '../blockRegistry'
import { CanvasContextKey } from '../useCanvasContext'
import { FIELD_ORDER, FIELD_LABEL, resolveRegion, fieldValue } from '@/lib/displayPolicy'
import type { DisplayField } from '~/types'

const props = defineProps<{
  block: EditorBlock
  number: number
}>()

const emit = defineEmits<{ change: []; 'view-detail': [] }>()

const ctx = inject(CanvasContextKey, { documentDisplay: null })

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
  <div class="group/q relative pl-8 pr-28 py-2 rounded-md hover:bg-muted/40 transition-colors">
    <!-- right-11 让开画布层右上角的删除按钮 (right-2) -->
    <div
      class="absolute right-11 top-1.5 flex items-center gap-1.5 opacity-0 group-hover/q:opacity-100 transition-opacity"
    >
      <div class="flex items-center gap-1">
        <Input
          v-model.number="score"
          type="number"
          min="0"
          step="0.5"
          placeholder="分值"
          class="h-7 w-16 text-xs"
        />
      </div>
      <Button variant="ghost" size="icon" class="h-7 w-7" title="查看题目" @click="emit('view-detail')">
        <Eye class="h-4 w-4" />
      </Button>
      <QuestionDisplayOverride :block="block" @change="emit('change')" />
    </div>

    <div class="flex gap-2">
      <span class="font-medium text-foreground shrink-0">{{ number }}.</span>
      <div class="flex-1 min-w-0 leading-relaxed">
        <MarkdownPreview v-if="q" :content="q.content" />
        <span v-else class="text-muted-foreground italic">题目已删除</span>
        <span v-if="score != null" class="ml-2 text-xs text-muted-foreground">（{{ score }} 分）</span>
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
