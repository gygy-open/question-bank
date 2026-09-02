<script setup lang="ts">
import { computed } from 'vue'
import type { RichDoc } from '@/types'
import { renderRichContentToHTML } from './renderRichContent'
import { isEmptyRichDoc } from './richDoc'

const props = withDefaults(
    defineProps<{
        content: RichDoc | null | undefined
        /** 内容为空时展示的占位文案；不传则空态渲染为空容器。 */
        emptyText?: string
        /** 外层容器附加 class（业务侧可传 prose 尺寸等）。 */
        class?: string
    }>(),
    { emptyText: '' },
)

const isEmpty = computed(() => isEmptyRichDoc(props.content))
const html = computed(() => renderRichContentToHTML(props.content))
</script>

<template>
    <div :class="['rich-content prose prose-sm dark:prose-invert max-w-none', props.class]">
        <span v-if="isEmpty && emptyText" class="text-muted-foreground">{{ emptyText }}</span>
        <div v-else-if="!isEmpty" v-html="html" />
    </div>
</template>

<style scoped>
.rich-content :deep(img) {
    max-width: 100%;
    height: auto;
}

.rich-content :deep(img[data-align='center']) {
    display: block;
    margin-left: auto;
    margin-right: auto;
}

.rich-content :deep(img[data-align='right']) {
    display: block;
    margin-left: auto;
}

.rich-content :deep(.rich-blank) {
    display: inline-block;
    min-width: 2em;
    height: 1em;
    margin: 0 0.15em;
    border-bottom: 1px solid currentColor;
    vertical-align: baseline;
}

/* 只读表格：与编辑器 ProseMirror 表格样式保持一致（prose 默认只有底边线，需补全网格线）。 */
.rich-content :deep(table) {
    border-collapse: collapse;
    table-layout: fixed;
    width: 100%;
    overflow: hidden;
}

.rich-content :deep(td),
.rich-content :deep(th) {
    vertical-align: top;
    box-sizing: border-box;
    border: 1px solid var(--border);
    padding: 0.35em 0.6em;
}

.rich-content :deep(th) {
    background-color: var(--muted);
    font-weight: 600;
    text-align: left;
}

</style>
