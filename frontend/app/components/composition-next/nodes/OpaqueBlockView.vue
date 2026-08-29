<script setup lang="ts">
// 不透明块占位 NodeView（Spike）：显示原节点类型，数据无损保存在 attrs.node。
import { computed } from 'vue'
import { NodeViewWrapper } from '@tiptap/vue-3'

const props = defineProps<{
  node: { attrs: Record<string, unknown> }
  selected?: boolean
}>()

const inner = computed(() => (props.node.attrs.node as { nodeType?: string } | null) ?? null)
</script>

<template>
  <NodeViewWrapper
    data-composition-block
    class="composition-opaque-block rounded-lg border border-dashed bg-muted/40 p-4 text-sm text-muted-foreground"
    :class="selected ? 'ring-2 ring-primary' : ''"
    contenteditable="false"
  >
    模块占位：{{ inner?.nodeType ?? 'unknown' }}（编辑能力将在后续阶段实现）
  </NodeViewWrapper>
</template>
