<script setup lang="ts">
import type { Editor } from '@tiptap/vue-3'
import { BubbleMenu } from '@tiptap/vue-3/menus'
import { Button } from '@/components/ui/button'
import { getInlineFormatItems } from './inlineFormatItems'
import { getImageAlignFormatItems } from './imageAlignFormatItems'
import RichEditorAlignMenu from './RichEditorAlignMenu.vue'

const props = defineProps<{ editor: Editor }>()

const items = getInlineFormatItems(props.editor)
const imageAlignItems = getImageAlignFormatItems(props.editor)

// 图片选中时只展示对齐按钮；question/questionDetails 等模块节点不展示气泡菜单。
const NO_BUBBLE_NODES = ['question', 'questionDetails']
function shouldShow({ editor, from, to }: { editor: Editor; from: number; to: number }): boolean {
    if (editor.isActive('image')) {
        return true
    }
    if (from === to) {
        return false
    }
    if (NO_BUBBLE_NODES.some((name) => editor.isActive(name))) {
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
            <template v-if="editor.isActive('image')">
                <Button
                    v-for="item in imageAlignItems"
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
            </template>
            <template v-else>
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
            </template>
        </div>
    </BubbleMenu>
</template>

