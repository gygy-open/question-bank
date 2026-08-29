<script setup lang="ts">
// 段落样式下拉（正文 / 标题 1-4）；仅在编辑器 schema 启用 heading 时由工具栏条件渲染。
import { computed } from 'vue'
import type { Editor } from '@tiptap/vue-3'
import { Button } from '@/components/ui/button'
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Heading, Check } from '@lucide/vue'

const props = defineProps<{ editor: Editor }>()

const LEVELS = [1, 2, 3, 4] as const

const items = computed(() => [
    {
        label: '正文',
        isActive: () => props.editor.isActive('paragraph'),
        action: () => props.editor.chain().focus().setParagraph().run(),
    },
    ...LEVELS.map((level) => ({
        label: `标题 ${level}`,
        isActive: () => props.editor.isActive('heading', { level }),
        action: () => props.editor.chain().focus().toggleHeading({ level }).run(),
    })),
])
const activeLabel = computed(() => items.value.find((i) => i.isActive())?.label ?? '正文')
</script>

<template>
    <DropdownMenu>
        <DropdownMenuTrigger as-child>
            <Button type="button" size="sm" class="h-8 gap-1 px-2" variant="ghost" title="段落样式">
                <Heading class="size-4" />
                <span class="text-xs">{{ activeLabel }}</span>
            </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
            <DropdownMenuItem
                v-for="item in items"
                :key="item.label"
                :class="item.isActive() ? 'bg-accent' : ''"
                @click="item.action"
            >
                <Check class="mr-2 size-4" :class="item.isActive() ? 'opacity-100' : 'opacity-0'" />
                {{ item.label }}
            </DropdownMenuItem>
        </DropdownMenuContent>
    </DropdownMenu>
</template>
