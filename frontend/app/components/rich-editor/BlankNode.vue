<script setup lang="ts">
import { computed, inject } from 'vue'
import { NodeViewWrapper, nodeViewProps } from '@tiptap/vue-3'
import { BLANK_EDITOR_KEY } from './blankEditorKey'
import { clampBlankWidthEm } from './schemaExtensions'

const props = defineProps(nodeViewProps)

const openBlankEditor = inject(BLANK_EDITOR_KEY, null)

const widthEm = computed(() => clampBlankWidthEm(props.node.attrs.widthEm))

function requestEdit(event: MouseEvent) {
    if (!props.editor.isEditable || !openBlankEditor) {
        return
    }
    const pos = typeof props.getPos === 'function' ? props.getPos() : null
    if (pos == null) {
        return
    }
    openBlankEditor({
        pos,
        widthEm: widthEm.value,
        anchorEl: event.currentTarget as HTMLElement,
    })
}
</script>

<template>
    <NodeViewWrapper
        as="span"
        contenteditable="false"
        class="rich-blank rich-blank--editable"
        :style="{ width: `${widthEm}em` }"
        role="img"
        aria-label="填空"
        @click="requestEdit"
    />
</template>
