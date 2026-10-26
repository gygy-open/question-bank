<script setup lang="ts">
import { computed } from 'vue'
import type { Editor } from '@tiptap/vue-3'
import { ImageIcon, List, ListOrdered, Music, Undo2, Redo2, Sigma, SquareSigma, SquareDashed } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip'
import { getInlineFormatItems, type ToolbarItem } from './inlineFormatItems'
import RichEditorAlignMenu from './RichEditorAlignMenu.vue'
import RichEditorHeadingMenu from './RichEditorHeadingMenu.vue'
import RichEditorTableMenu from './RichEditorTableMenu.vue'

const props = defineProps<{ editor: Editor; allowBlank?: boolean; allowHeading?: boolean; allowAudio?: boolean }>()
const emit = defineEmits<{
    image: []
    audio: []
    math: [boolean]
    blank: []
    table: [{ rows: number; cols: number; withHeaderRow: boolean }]
}>()

const { t } = useI18n()

const inlineItems = getInlineFormatItems(props.editor)

// 段落：列表（对齐菜单在模板里单独渲染）。
const paragraphItems: ToolbarItem[] = [
    {
        labelKey: 'richEditor.slash.items.bulletList',
        icon: List,
        action: () => props.editor.chain().focus().toggleBulletList().run(),
        isActive: () => props.editor.isActive('bulletList'),
    },
    {
        labelKey: 'richEditor.slash.items.orderedList',
        icon: ListOrdered,
        action: () => props.editor.chain().focus().toggleOrderedList().run(),
        isActive: () => props.editor.isActive('orderedList'),
    },
]

// 插入：公式 / 图片 /（表格单独渲染，需要弹出行列选择）/（填空）。
const insertItems = computed<ToolbarItem[]>(() => {
    const items: ToolbarItem[] = [
        { labelKey: 'richEditor.slash.items.inlineMath', icon: Sigma, action: () => emit('math', false) },
        { labelKey: 'richEditor.slash.items.blockMath', icon: SquareSigma, action: () => emit('math', true) },
        { labelKey: 'richEditor.slash.items.image', icon: ImageIcon, action: () => emit('image') },
    ]
    if (props.allowAudio) {
        items.push({ labelKey: 'richEditor.slash.items.audio', icon: Music, action: () => emit('audio') })
    }
    if (props.allowBlank) {
        items.push({ labelKey: 'richEditor.toolbar.insertBlank', icon: SquareDashed, action: () => emit('blank') })
    }
    return items
})

const historyGroup: ToolbarItem[] = [
    {
        labelKey: 'richEditor.toolbar.undo',
        icon: Undo2,
        action: () => props.editor.chain().focus().undo().run(),
        disabled: () => !props.editor.can().undo(),
    },
    {
        labelKey: 'richEditor.toolbar.redo',
        icon: Redo2,
        action: () => props.editor.chain().focus().redo().run(),
        disabled: () => !props.editor.can().redo(),
    },
]
</script>

<template>
    <TooltipProvider :delay-duration="300">
        <div class="flex flex-wrap items-center gap-0.5 border-b border-border p-1">
            <!-- 段落样式 -->
            <template v-if="allowHeading">
                <RichEditorHeadingMenu :editor="editor" />
                <div aria-hidden="true" class="mx-1 h-6 w-px shrink-0 bg-border" />
            </template>
            <!-- 文本 -->
            <Tooltip v-for="item in inlineItems" :key="item.labelKey">
                <TooltipTrigger as-child>
                    <Button
                        type="button"
                        size="icon"
                        class="size-8"
                        :variant="item.isActive?.() ? 'secondary' : 'ghost'"
                        :disabled="item.disabled?.()"
                        @click="item.action"
                    >
                        <component :is="item.icon" class="size-4" />
                    </Button>
                </TooltipTrigger>
                <TooltipContent>{{ t(item.labelKey) }}</TooltipContent>
            </Tooltip>

            <div aria-hidden="true" class="mx-1 h-6 w-px shrink-0 bg-border" />
            <!-- 段落 -->
            <RichEditorAlignMenu :editor="editor" />
            <Tooltip v-for="item in paragraphItems" :key="item.labelKey">
                <TooltipTrigger as-child>
                    <Button
                        type="button"
                        size="icon"
                        class="size-8"
                        :variant="item.isActive?.() ? 'secondary' : 'ghost'"
                        @click="item.action"
                    >
                        <component :is="item.icon" class="size-4" />
                    </Button>
                </TooltipTrigger>
                <TooltipContent>{{ t(item.labelKey) }}</TooltipContent>
            </Tooltip>

            <div aria-hidden="true" class="mx-1 h-6 w-px shrink-0 bg-border" />
            <!-- 插入 -->
            <Tooltip v-for="item in insertItems" :key="item.labelKey">
                <TooltipTrigger as-child>
                    <Button
                        type="button"
                        size="icon"
                        class="size-8"
                        variant="ghost"
                        @mousedown.prevent
                        @click="item.action"
                    >
                        <component :is="item.icon" class="size-4" />
                    </Button>
                </TooltipTrigger>
                <TooltipContent>{{ t(item.labelKey) }}</TooltipContent>
            </Tooltip>
            <RichEditorTableMenu @insert="(options) => emit('table', options)" />

            <template v-if="$slots.default">
                <div aria-hidden="true" class="mx-1 h-6 w-px shrink-0 bg-border" />
                <slot />
            </template>

            <div class="ml-auto flex items-center gap-0.5">
                <Tooltip v-for="item in historyGroup" :key="item.labelKey">
                    <TooltipTrigger as-child>
                        <Button
                            type="button"
                            size="icon"
                            class="size-8"
                            variant="ghost"
                            :disabled="item.disabled?.()"
                            @click="item.action"
                        >
                            <component :is="item.icon" class="size-4" />
                        </Button>
                    </TooltipTrigger>
                    <TooltipContent>{{ t(item.labelKey) }}</TooltipContent>
                </Tooltip>
            </div>
        </div>
    </TooltipProvider>
</template>
