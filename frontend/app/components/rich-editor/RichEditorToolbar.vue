<script setup lang="ts">
import { computed } from 'vue'
import type { Editor } from '@tiptap/vue-3'
import { ImageIcon, List, ListOrdered, Undo2, Redo2, Sigma, SquareSigma, SquareDashed, Table as TableIcon } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip'
import { getInlineFormatItems, type ToolbarItem } from './inlineFormatItems'
import RichEditorAlignMenu from './RichEditorAlignMenu.vue'

const props = defineProps<{ editor: Editor; allowBlank?: boolean }>()
const emit = defineEmits<{ image: []; math: [boolean]; blank: []; table: [] }>()

const inlineItems = getInlineFormatItems(props.editor)

const insertGroup = computed<ToolbarItem[]>(() => {
    const items: ToolbarItem[] = [
        {
            label: '插入表格',
            icon: TableIcon,
            action: () => emit('table'),
        },
    ]
    if (props.allowBlank) {
        items.push({
            label: '插入填空',
            icon: SquareDashed,
            action: () => emit('blank'),
        })
    }
    return items
})

const groups: ToolbarItem[][] = [
    inlineItems.slice(0, 3), // 加粗 斜体 下划线
    inlineItems.slice(3), // 上标 下标 清除格式
    [
        {
            label: '行内公式',
            icon: Sigma,
            action: () => emit('math', false),
        },
        {
            label: '块公式',
            icon: SquareSigma,
            action: () => emit('math', true),
        },
    ],
    [
        {
            label: '图片',
            icon: ImageIcon,
            action: () => emit('image'),
        },
    ],
    [
        {
            label: '无序列表',
            icon: List,
            action: () => props.editor.chain().focus().toggleBulletList().run(),
            isActive: () => props.editor.isActive('bulletList'),
        },
        {
            label: '有序列表',
            icon: ListOrdered,
            action: () => props.editor.chain().focus().toggleOrderedList().run(),
            isActive: () => props.editor.isActive('orderedList'),
        },
    ],
]

const historyGroup: ToolbarItem[] = [
    {
        label: '撤销',
        icon: Undo2,
        action: () => props.editor.chain().focus().undo().run(),
        disabled: () => !props.editor.can().undo(),
    },
    {
        label: '重做',
        icon: Redo2,
        action: () => props.editor.chain().focus().redo().run(),
        disabled: () => !props.editor.can().redo(),
    },
]
</script>

<template>
    <TooltipProvider :delay-duration="300">
        <div class="flex flex-wrap items-center gap-0.5 border-b border-border p-1">
            <template v-for="(group, gi) in groups" :key="gi">
                <Separator v-if="gi > 0" orientation="vertical" class="mx-1 h-6" />
                <template v-if="gi === 2">
                    <RichEditorAlignMenu :editor="editor" />
                    <Separator orientation="vertical" class="mx-1 h-6" />
                </template>
                <Tooltip v-for="item in group" :key="item.label">
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
                    <TooltipContent>{{ item.label }}</TooltipContent>
                </Tooltip>
            </template>

            <Separator orientation="vertical" class="mx-1 h-6" />
            <Tooltip v-for="item in insertGroup" :key="item.label">
                <TooltipTrigger as-child>
                    <Button
                        type="button"
                        size="icon"
                        class="size-8"
                        variant="ghost"
                        @click="item.action"
                    >
                        <component :is="item.icon" class="size-4" />
                    </Button>
                </TooltipTrigger>
                <TooltipContent>{{ item.label }}</TooltipContent>
            </Tooltip>

            <div class="ml-auto flex items-center gap-0.5">
                <Tooltip v-for="item in historyGroup" :key="item.label">
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
                    <TooltipContent>{{ item.label }}</TooltipContent>
                </Tooltip>
            </div>
        </div>
    </TooltipProvider>
</template>
