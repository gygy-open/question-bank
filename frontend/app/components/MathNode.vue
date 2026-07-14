<script setup lang="ts">
import { computed } from 'vue'
import { nodeViewProps, NodeViewWrapper } from '@tiptap/vue-3'
import katex from 'katex'
import 'katex/dist/katex.min.css'

const props = defineProps(nodeViewProps)

const renderedLatex = computed(() => {
  try {
    return katex.renderToString(props.node.attrs.latex || '', {
      throwOnError: false,
      displayMode: props.node.attrs.display
    })
  } catch (e) {
    return props.node.attrs.latex
  }
})

const handleClick = () => {
  if (typeof props.extension.options.onEdit === 'function') {
    props.extension.options.onEdit({
      latex: props.node.attrs.latex,
      display: props.node.attrs.display,
      update: (attrs: any) => props.updateAttributes(attrs)
    })
  }
}
</script>

<template>
  <node-view-wrapper as="span" 
    class="math-node inline-block cursor-pointer hover:bg-muted/20 rounded px-0.5 transition-colors select-none" 
    :class="{ 'ring-2 ring-primary ring-offset-1': selected }"
    @click="handleClick"
  >
    <span v-html="renderedLatex"></span>
  </node-view-wrapper>
</template>

<style>
.math-node {
  vertical-align: middle;
}
</style>