<script setup lang="ts">
import { computed, provide, ref } from 'vue'
import draggable from 'vuedraggable'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { GripVertical, Trash2 } from '@lucide/vue'
import type { BlockType } from '~/types'
import BlockInserter from './BlockInserter.vue'
import {
  getBlockComponent,
  getBlockMenu,
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

/** 题号: 题块自定义题号优先于文档级策略; 其余由文档级编号策略决定是否编号、遇标题是否重置、是否按 H2~H4 生成层级题号。 */
const displayNumbers = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  const numbering = props.context.documentNumbering
  const autoNumber = numbering?.auto !== false
  const scope = numbering?.scope ?? 'section'

  // 题块自定义题号: 直接使用该字符串 (哪怕是空串), 不占用计数器, 不受"自动编号"总开关影响
  const labelOverrideOf = (b: EditorBlock): string | undefined => b.content?.label_override

  // 层级编号: 只用 H2~H4 三级 (H1 是页面标题概念, 不参与), 遇标题按层级截断/递增, 题目在当前路径下顺序递增
  if (scope === 'outline') {
    const path: number[] = []
    let leaf = 0
    for (const b of props.modelValue) {
      if (b.block_type === 'heading') {
        const level = b.content?.level ?? 2
        if (level >= 2) {
          const idx = level - 2
          const current = (idx < path.length ? path[idx] : 0) ?? 0
          path.length = idx
          path.push(current + 1)
          leaf = 0
        }
        continue
      }
      if (b.block_type === 'question') {
        const override = labelOverrideOf(b)
        if (override !== undefined) {
          map[b.key] = override
          continue
        }
        if (!autoNumber) continue
        leaf += 1
        map[b.key] = [...path, leaf].join('.')
      }
    }
    return map
  }

  const resetOnHeading = scope !== 'document'
  let counter = 0
  for (const b of props.modelValue) {
    if (b.block_type === 'heading') {
      if (resetOnHeading) counter = 0
      continue
    }
    if (b.block_type === 'question') {
      const override = labelOverrideOf(b)
      if (override !== undefined) {
        map[b.key] = override
        continue
      }
      if (!autoNumber) continue
      counter += 1
      map[b.key] = String(counter)
    }
  }
  return map
})

// 手柄单击开菜单、按住拖动排序 (类 Notion); justDragged 用来吞掉拖拽松手后浏览器补发的那次 click
const openMenuKey = ref<string | null>(null)
let justDragged = false

const onDragStart = () => { justDragged = true }
const onDragEnd = () => {
  emit('change')
  setTimeout(() => { justDragged = false }, 0)
}

const onMenuOpenChange = (open: boolean, key: string) => {
  if (open && justDragged) return
  openMenuKey.value = open ? key : null
}

const resolveBlocks = (payload: BlockType | EditorBlock | EditorBlock[]): EditorBlock[] => {
  if (typeof payload === 'string') return [newEditorBlock(payload)]
  return Array.isArray(payload) ? payload : [payload]
}

const insertAfter = (index: number, payload: BlockType | EditorBlock | EditorBlock[]) => {
  const next = [...props.modelValue]
  next.splice(index + 1, 0, ...resolveBlocks(payload))
  emit('update:modelValue', next)
  emit('change')
}

const insertAtStart = (payload: BlockType | EditorBlock | EditorBlock[]) => {
  emit('update:modelValue', [...resolveBlocks(payload), ...props.modelValue])
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
    <!-- 顶部插入: 空文档时是唯一入口, 常驻显示; 有内容时挪到第一个块的悬浮区里 (见下方 index === 0 分支) -->
    <div
      v-if="modelValue.length === 0"
      class="flex justify-center mb-2 opacity-60 hover:opacity-100 transition-opacity"
    >
      <BlockInserter @insert="insertAtStart" />
    </div>

    <draggable
      v-model="blocks"
      item-key="key"
      handle=".block-drag-handle"
      :animation="200"
      @start="onDragStart"
      @end="onDragEnd"
    >
      <template #item="{ element, index }">
        <div class="group/block relative">
          <!-- 首块顶部插入: 平时隐藏, 悬浮第一个块才出现, 和下方"块间插入"手感一致 -->
          <div
            v-if="index === 0"
            class="flex justify-center mb-1 opacity-0 group-hover/block:opacity-100 transition-opacity"
          >
            <BlockInserter @insert="insertAtStart" />
          </div>

          <!-- 拖拽手柄: 按住拖动排序; 单击弹出块操作菜单 (删除等), open 态受控以便吞掉拖拽后的补发 click -->
          <DropdownMenu
            :open="openMenuKey === element.key"
            @update:open="(v) => onMenuOpenChange(v, element.key)"
          >
            <DropdownMenuTrigger as-child>
              <div
                class="block-drag-handle absolute left-0 top-2.5 cursor-move opacity-0 group-hover/block:opacity-60 hover:!opacity-100 transition-opacity z-10"
              >
                <GripVertical class="h-5 w-5 text-muted-foreground" />
              </div>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start">
              <component
                :is="getBlockMenu(element.block_type)"
                v-if="getBlockMenu(element.block_type)"
                :block="element"
                @change="emit('change')"
                @view-detail="emit('view-detail', element)"
              />
              <DropdownMenuItem variant="destructive" @click="removeBlock(index)">
                <Trash2 /> 删除
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>

          <!-- 动态块 -->
          <component
            :is="getBlockComponent(element.block_type)"
            :block="element"
            :number="displayNumbers[element.key]"
            @change="emit('change')"
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
