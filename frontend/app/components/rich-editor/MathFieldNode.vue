<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import katex from 'katex'
import { NodeViewWrapper, nodeViewProps } from '@tiptap/vue-3'
import { MathfieldElement } from 'mathlive'
import 'mathlive/static.css'
import { consumeMathAutofocus } from './mathFieldExtensions'

// 关闭 MathLive 默认音效，避免请求并不存在的 .wav 资源（控制台 404）。
if (typeof window !== 'undefined') {
    MathfieldElement.soundsDirectory = null
}

const props = defineProps(nodeViewProps)

const isBlock = computed(() => props.node.type.name === 'blockMath')
const latex = computed<string>(() => (props.node.attrs.latex as string) || '')
const editing = ref(false)
const mathfieldRef = ref<HTMLElement | null>(null)

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

function startEdit() {
    if (!props.editor.isEditable || editing.value) {
        return
    }
    editing.value = true
    nextTick(() => {
        const mf = mathfieldRef.value as unknown as { value: string; focus: () => void } | null
        if (!mf) return
        mf.value = latex.value
        mf.focus()
    })
}

function currentValue(): string {
    const mf = mathfieldRef.value as unknown as { value?: string } | null
    return mf ? String(mf.value ?? '').trim() : ''
}

function commit() {
    if (!editing.value) {
        return
    }
    const value = currentValue()
    editing.value = false
    if (!value) {
        props.deleteNode()
        return
    }
    if (value !== latex.value) {
        props.updateAttributes({ latex: value })
    }
    props.editor.commands.focus()
}

function cancel() {
    const wasEmpty = !latex.value
    editing.value = false
    if (wasEmpty) {
        props.deleteNode()
    } else {
        props.editor.commands.focus()
    }
}

function onKeydown(event: KeyboardEvent) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault()
        commit()
    } else if (event.key === 'Escape') {
        event.preventDefault()
        event.stopPropagation()
        cancel()
    }
}

// MathLive 虚拟键盘渲染在 math-field 之外，点击它会触发 focusout；
// 延迟一拍后若焦点仍在输入框/虚拟键盘内、或虚拟键盘可见，则不提交，避免键盘与输入框一起闪退。
function isKeyboardEl(el: Element | null): boolean {
    return !!el?.closest?.('[class*="ML__keyboard"], [class*="MLK__"]')
}
function onFocusOut() {
    window.setTimeout(() => {
        if (!editing.value) return
        const mf = mathfieldRef.value
        const active = document.activeElement
        if (mf && active && (active === mf || mf.contains(active))) return
        if (isKeyboardEl(active)) return
        const vk = (window as unknown as { mathVirtualKeyboard?: { visible?: boolean } }).mathVirtualKeyboard
        if (vk?.visible) return
        commit()
    }, 0)
}

onMounted(() => {
    // 新插入的空公式自动进入行内编辑（插入时打的标记）；页面加载的持久空节点不自动抢焦点。
    if (props.editor.isEditable && !latex.value && consumeMathAutofocus()) {
        startEdit()
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
        <math-field
            v-if="editing"
            ref="mathfieldRef"
            class="rich-math__field"
            @keydown="onKeydown"
            @focusout="onFocusOut"
        />
        <span v-else class="rich-math__display" @click="startEdit">
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
.rich-math__field {
    display: inline-block;
    min-width: 14rem;
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 2px 6px;
    background-color: var(--background);
}
.rich-math--block .rich-math__field {
    display: block;
    min-width: 24rem;
}
</style>
