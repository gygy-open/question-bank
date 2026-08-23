<script setup lang="ts">
import { ref, computed, inject, onMounted } from 'vue'
import katex from 'katex'
import { NodeViewWrapper, nodeViewProps } from '@tiptap/vue-3'
import type { OpenMathEditor } from './mathEditorKey'
import { MATH_EDITOR_KEY } from './mathEditorKey'

const props = defineProps(nodeViewProps)

const openMathEditor = inject<OpenMathEditor | null>(MATH_EDITOR_KEY, null)

const isBlock = computed(() => props.node.type.name === 'blockMath')
const latex = computed<string>(() => (props.node.attrs.latex as string) || '')
const displayRef = ref<HTMLElement | null>(null)

const rendered = computed(() => {
    try {
        return katex.renderToString(latex.value, {
            throwOnError: false,
            displayMode: isBlock.value,
        })
    } catch {
        return latex.value
    }
})

function requestEdit() {
    if (!props.editor.isEditable || !openMathEditor) {
        return
    }
    const pos = typeof props.getPos === 'function' ? props.getPos() : null
    if (pos == null) {
        return
    }
    openMathEditor({
        pos,
        isBlock: isBlock.value,
        latex: latex.value,
        anchorEl: displayRef.value,
    })
}

onMounted(() => {
    // 新插入的空公式自动进入编辑
    if (props.editor.isEditable && !latex.value) {
        requestEdit()
    }
})
</script>

<template>
    <NodeViewWrapper
        :as="isBlock ? 'div' : 'span'"
        contenteditable="false"
        class="rich-math"
        :class="isBlock ? 'rich-math--block' : 'rich-math--inline'"
    >
        <span ref="displayRef" class="rich-math__display" @click="requestEdit">
            <span v-if="latex" v-html="rendered" />
            <span v-else class="rich-math__placeholder">点击输入公式</span>
        </span>
    </NodeViewWrapper>
</template>

<style>
.rich-math--inline {
    display: inline-block;
}
.rich-math--block {
    display: block;
    margin: 0.5rem 0;
    text-align: center;
}
.rich-math__display {
    cursor: pointer;
    border-radius: 4px;
    padding: 0 2px;
}
.rich-math__display:hover {
    background-color: var(--accent);
}
.rich-math__placeholder {
    color: var(--muted-foreground);
    font-size: 0.875em;
}
</style>
