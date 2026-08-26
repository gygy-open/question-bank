<script setup lang="ts">
import { ref, watch } from 'vue'
import type { SuggestionKeyDownProps } from '@tiptap/suggestion'
import type { SlashCommandItem } from './SlashCommand'

const props = defineProps<{
    items: SlashCommandItem[]
    command: (item: SlashCommandItem) => void
}>()

const selectedIndex = ref(0)

watch(
    () => props.items,
    () => {
        selectedIndex.value = 0
    },
)

function selectItem(index: number) {
    const item = props.items[index]
    if (item) {
        props.command(item)
    }
}

function onKeyDown({ event }: SuggestionKeyDownProps): boolean {
    if (!props.items.length) {
        return false
    }

    if (event.key === 'ArrowUp') {
        selectedIndex.value = (selectedIndex.value + props.items.length - 1) % props.items.length
        return true
    }
    if (event.key === 'ArrowDown') {
        selectedIndex.value = (selectedIndex.value + 1) % props.items.length
        return true
    }
    if (event.key === 'Enter') {
        selectItem(selectedIndex.value)
        return true
    }
    return false
}

defineExpose({ onKeyDown })
</script>

<template>
    <div
        data-rich-overlay
        class="z-50 max-h-80 w-56 overflow-y-auto rounded-md border border-border bg-popover p-1 text-popover-foreground shadow-md"
    >
        <template v-if="items.length">
            <button
                v-for="(item, index) in items"
                :key="item.title"
                type="button"
                :class="[
                    'flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm transition-colors',
                    index === selectedIndex ? 'bg-accent text-accent-foreground' : 'hover:bg-accent/50',
                ]"
                @click="selectItem(index)"
                @mouseenter="selectedIndex = index"
            >
                <component :is="item.icon" class="size-4 shrink-0" />
                <span>{{ item.title }}</span>
            </button>
        </template>
        <div v-else class="px-2 py-1.5 text-sm text-muted-foreground">无匹配结果</div>
    </div>
</template>
