<script setup lang="ts">
import { computed } from 'vue'
import type { Editor } from '@tiptap/vue-3'
import { Button } from '@/components/ui/button'
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { getAlignFormatItems } from './alignFormatItems'

const props = defineProps<{ editor: Editor }>()
const { t } = useI18n()

const items = getAlignFormatItems(props.editor)
const activeItem = computed(() => items.find((item) => item.isActive?.()) ?? items[0]!)
</script>

<template>
    <DropdownMenu>
        <DropdownMenuTrigger as-child>
            <Button type="button" size="icon" class="size-8" variant="ghost" :title="t('richEditor.align.title')">
                <component :is="activeItem.icon" class="size-4" />
            </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
            <DropdownMenuItem
                v-for="item in items"
                :key="item.labelKey"
                :class="item.isActive?.() ? 'bg-accent' : ''"
                @click="item.action"
            >
                <component :is="item.icon" class="mr-2 size-4" />
                {{ t(item.labelKey) }}
            </DropdownMenuItem>
        </DropdownMenuContent>
    </DropdownMenu>
</template>
