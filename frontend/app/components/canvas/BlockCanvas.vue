<script setup lang="ts">
import { computed, provide } from 'vue'
import draggable from 'vuedraggable'
import { Button } from '@/components/ui/button'
import { GripVertical, Trash2 } from '@lucide/vue'
import type { BlockType } from '~/types'
import BlockInserter from './BlockInserter.vue'
import {
  getBlockComponent,
  newEditorBlock,
  type EditorBlock,
} from './blockRegistry'
import { CanvasContextKey, type CanvasContext } from './useCanvasContext'

const props = defineProps<{
  modelValue: EditorBlock[]
  context: CanvasContext
}>()

const emit = defineEmits<{
  'update:modelValue': [blocks: EditorBlock[]]
  change: []
  'view-detail': [block: EditorBlock]
}>()

provide(CanvasContextKey, props.context)

const blocks = computed({
  get: () => props.modelValue,
  set: (v: EditorBlock[]) => emit('update:modelValue', v),
})

/** 题号: 每遇到大题标题重置计数。 */
const displayNumbers = computed<Record<string, number>>(() => {
  const map: Record<string, number> = {}
  let counter = 0
  for (const b of props.modelValue) {
    if (b.block_type === 'heading') {
      counter = 0
      continue
    }
    if (b.block_type === 'question') {
      counter += 1
      map[b.key] = counter
    }
  }
  return map
})

const onDragEnd = () => emit('change')

const insertAfter = (index: number, type: BlockType) => {
  const next = [...props.modelValue]
  next.splice(index + 1, 0, newEditorBlock(type))
  emit('update:modelValue', next)
  emit('change')
}

const insertAtStart = (type: BlockType) => {
  emit('update:modelValue', [newEditorBlock(type), ...props.modelValue])
  emit('change')
}

const removeBlock = (index: number) => {
  const next = [...props.modelValue]
  next.splice(index, 1)
  emit('update:modelValue', next)
  emit('change')
}

defineExpose({ insertAtStart })
</script>

<template>
  <div>
    <!-- 顶部插入 -->
    <div class="flex justify-center mb-2 opacity-60 hover:opacity-100 transition-opacity">
      <BlockInserter @insert="insertAtStart" />
    </div>

    <draggable
      v-model="blocks"
      item-key="key"
      handle=".block-drag-handle"
      :animation="200"
      @end="onDragEnd"
    >
      <template #item="{ element, index }">
        <div class="group/block relative">
          <!-- 拖拽手柄 -->
          <div
            class="block-drag-handle absolute left-0 top-2.5 cursor-move opacity-0 group-hover/block:opacity-60 hover:!opacity-100 transition-opacity z-10"
          >
            <GripVertical class="h-5 w-5 text-muted-foreground" />
          </div>

          <!-- 删除 -->
          <Button
            variant="ghost"
            size="icon"
            class="absolute right-2 top-1.5 h-7 w-7 text-destructive hover:text-destructive opacity-0 group-hover/block:opacity-100 transition-opacity z-10"
            title="删除此块"
            @click="removeBlock(index)"
          >
            <Trash2 class="h-4 w-4" />
          </Button>

          <!-- 动态块 -->
          <component
            :is="getBlockComponent(element.block_type)"
            :block="element"
            :number="displayNumbers[element.key]"
            @change="emit('change')"
            @view-detail="emit('view-detail', element)"
          />

          <!-- 块间插入 -->
          <div
            class="flex justify-center my-1 opacity-0 group-hover/block:opacity-100 transition-opacity"
          >
            <BlockInserter @insert="(t) => insertAfter(index, t)" />
          </div>
        </div>
      </template>
    </draggable>
  </div>
</template>
