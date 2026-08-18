<script setup lang="ts">
import { ref, inject } from 'vue'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Button } from '@/components/ui/button'
import { Plus, ChevronLeft, FileQuestion, Blocks, Loader2 } from '@lucide/vue'
import { insertableBlocks, newQuestionBlock, toEditorBlock, type EditorBlock } from './blockRegistry'
import { CanvasContextKey } from './useCanvasContext'
import QuestionPicker from './QuestionPicker.vue'
import ModulePicker from './ModulePicker.vue'
import { useCompositions } from '~/composables/useCompositions'
import { toast } from 'vue-sonner'
import type { BlockType, QuestionBrief, Composition } from '~/types'

const emit = defineEmits<{ insert: [block: EditorBlock | EditorBlock[] | BlockType] }>()
const { get } = useCompositions()
const open = ref(false)
const mode = ref<'menu' | 'question' | 'module'>('menu')
const cloning = ref(false)

const ctx = inject(CanvasContextKey, { documentDisplay: null })

const onOpenChange = (v: boolean) => {
  open.value = v
  if (v) mode.value = 'menu'
}

const pickStatic = (type: BlockType) => {
  open.value = false
  emit('insert', type)
}

const pickQuestion = (q: QuestionBrief) => {
  open.value = false
  emit('insert', newQuestionBlock(q))
}

/** 克隆其他文档: 深拷贝其全部块, 与源解耦, 可直接修改。 */
const pickModule = async (c: Composition) => {
  cloning.value = true
  try {
    const detail = await get(c.id)
    open.value = false
    emit('insert', detail.blocks.map(toEditorBlock))
  } catch {
    toast.error('导入文档内容失败')
  } finally {
    cloning.value = false
  }
}
</script>

<template>
  <Popover :open="open" @update:open="onOpenChange">
    <PopoverTrigger as-child>
      <Button variant="secondary" size="sm" class="h-6 px-2 text-xs shadow-sm">
        <Plus class="mr-1 h-3 w-3" /> 插入内容
      </Button>
    </PopoverTrigger>
    <PopoverContent class="w-56 p-1" align="center">
      <template v-if="mode === 'menu'">
        <button
          class="w-full flex items-center gap-2 px-2 py-1.5 text-sm rounded-md hover:bg-muted transition-colors text-left"
          @click="mode = 'question'"
        >
          <FileQuestion class="h-4 w-4 text-muted-foreground" /> 题目
        </button>
        <button
          class="w-full flex items-center gap-2 px-2 py-1.5 text-sm rounded-md hover:bg-muted transition-colors text-left"
          @click="mode = 'module'"
        >
          <Blocks class="h-4 w-4 text-muted-foreground" /> 克隆文档
        </button>
        <button
          v-for="b in insertableBlocks"
          :key="b.type"
          class="w-full flex items-center gap-2 px-2 py-1.5 text-sm rounded-md hover:bg-muted transition-colors text-left"
          @click="pickStatic(b.type)"
        >
          <component :is="b.icon" class="h-4 w-4 text-muted-foreground" />
          {{ b.label }}
        </button>
      </template>

      <template v-else>
        <button
          class="mb-1 flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          @click="mode = 'menu'"
        >
          <ChevronLeft class="h-3 w-3" /> 返回
        </button>
        <QuestionPicker v-if="mode === 'question'" :active="mode === 'question'" @pick="pickQuestion" />
        <div v-else-if="cloning" class="flex justify-center py-6">
          <Loader2 class="h-4 w-4 animate-spin text-muted-foreground" />
        </div>
        <ModulePicker v-else :active="mode === 'module'" :exclude-id="ctx.compId" @pick="pickModule" />
      </template>
    </PopoverContent>
  </Popover>
</template>
