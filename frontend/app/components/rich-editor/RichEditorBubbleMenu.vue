<script setup lang="ts">
import type { Editor } from '@tiptap/vue-3'
import { BubbleMenu } from '@tiptap/vue-3/menus'
import { Button } from '@/components/ui/button'
import { getInlineFormatItems } from './inlineFormatItems'
import RichEditorAlignMenu from './RichEditorAlignMenu.vue'

const props = defineProps<{ editor: Editor }>()

const items = getInlineFormatItems(props.editor)

// 仅在存在非空文本选区时浮出；图片/题目/模块等 atom 节点选中不显示。
const ATOM_NODES = ['image', 'question', 'questionDetails']
function shouldShow({ editor, from, to }: { editor: Editor; from: number; to: number }): boolean {
    if (from === to) {
        return false
    }
    if (ATOM_NODES.some((name) => editor.isActive(name))) {
        return false
    }
    return true
}
</script>

<template>
    <BubbleMenu
        :editor="editor"
        :should-show="shouldShow"
        :options="{ placement: 'top', offset: 8 }"
    >
        <div
            class="flex items-center gap-0.5 rounded-md border border-border bg-popover p-1 text-popover-foreground shadow-md"
        >
            <Button
                v-for="item in items"
                :key="item.label"
                type="button"
                size="icon"
                class="size-8"
                :variant="item.isActive?.() ? 'secondary' : 'ghost'"
                :title="item.label"
                @click="item.action"
            >
                <component :is="item.icon" class="size-4" />
            </Button>
            <RichEditorAlignMenu :editor="editor" />
        </div>
    </BubbleMenu>
</template>
