<script setup lang="ts">
import { computed, inject } from 'vue'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Eye } from '@lucide/vue'
import MarkdownPreview from '@/components/MarkdownPreview.vue'
import type { EditorBlock } from '../blockRegistry'
import { CanvasContextKey } from '../useCanvasContext'

const props = defineProps<{
  block: EditorBlock
  number: number
}>()

const emit = defineEmits<{ change: []; 'view-detail': [] }>()

const ctx = inject(CanvasContextKey, { showAnswers: false })

const q = computed(() => props.block.question)
const isChoice = computed(
  () => q.value?.q_type === 'single_choice' || q.value?.q_type === 'multiple_choice',
)
const options = computed(() => q.value?.options || [])

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
  <div class="group/q relative pl-8 pr-16 py-2 rounded-md hover:bg-muted/40 transition-colors">
    <div
      class="absolute right-2 top-1.5 flex items-center gap-2 opacity-0 group-hover/q:opacity-100 transition-opacity"
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

    <!-- 学案/题组: 展示答案与解析 -->
    <div v-if="ctx.showAnswers && q" class="mt-2 pl-6 space-y-1 text-sm">
      <div v-if="q.answer" class="text-foreground">
        <span class="font-medium">【答案】</span>
        <MarkdownPreview :content="q.answer" class="inline [&_.prose]:my-0 [&_.prose>p]:my-0" />
      </div>
      <div v-if="q.analysis" class="text-muted-foreground">
        <span class="font-medium">【解析】</span>
        <MarkdownPreview :content="q.analysis" class="inline [&_.prose]:my-0 [&_.prose>p]:my-0" />
      </div>
    </div>
  </div>
</template>
