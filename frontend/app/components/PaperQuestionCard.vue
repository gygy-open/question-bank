<script setup lang="ts">
import { computed } from 'vue'
import { Button } from '@/components/ui/button'
import { GripVertical, Eye, X } from 'lucide-vue-next'
import MarkdownPreview from '@/components/MarkdownPreview.vue'
import type { PaperItem } from '~/types'

const props = defineProps<{
  item: PaperItem
  number: number
}>()

const emit = defineEmits<{
  remove: []
  'view-detail': []
}>()

const isChoice = computed(
  () => props.item.question?.q_type === 'single_choice'
    || props.item.question?.q_type === 'multiple_choice',
)

const options = computed(() => props.item.question?.options || [])
</script>

<template>
  <div>
    <!-- 题目行 -->
    <div class="group relative pl-8 pr-16 py-2 rounded-md hover:bg-muted/40 transition-colors">
      <!-- 拖拽手柄 -->
      <div
        class="drag-handle absolute left-0 top-2 cursor-move opacity-0 group-hover:opacity-60 hover:!opacity-100 transition-opacity"
      >
        <GripVertical class="h-5 w-5 text-muted-foreground" />
      </div>

      <!-- 悬停操作按钮 -->
      <div
        class="absolute right-2 top-1.5 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity"
      >
        <Button variant="ghost" size="icon" class="h-7 w-7" title="查看题目" @click="emit('view-detail')">
          <Eye class="h-4 w-4" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          class="h-7 w-7 text-destructive hover:text-destructive"
          title="移除"
          @click="emit('remove')"
        >
          <X class="h-4 w-4" />
        </Button>
      </div>

      <!-- 题干 -->
      <div class="flex gap-2">
        <span class="font-medium text-foreground shrink-0">{{ number }}.</span>
        <div class="flex-1 min-w-0 leading-relaxed">
          <MarkdownPreview v-if="item.question" :content="item.question.content" />
          <span v-else class="text-muted-foreground italic">题目已删除</span>
        </div>
      </div>

      <!-- 选项（选择题） -->
      <div v-if="isChoice && options.length > 0" class="mt-2 pl-6 space-y-1.5">
        <div v-for="opt in options" :key="opt.label" class="flex gap-2">
          <span class="font-medium text-foreground shrink-0">{{ opt.label }}.</span>
          <div class="flex-1 min-w-0 [&_.prose]:my-0 [&_.prose>p]:my-0">
            <MarkdownPreview :content="opt.content" />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
