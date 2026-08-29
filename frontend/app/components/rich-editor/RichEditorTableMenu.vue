<script setup lang="ts">
import { ref } from 'vue'
import { Table as TableIcon } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Checkbox } from '@/components/ui/checkbox'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

const emit = defineEmits<{ insert: [{ rows: number; cols: number; withHeaderRow: boolean }] }>()

const open = ref(false)
const rows = ref(3)
const cols = ref(3)
const withHeaderRow = ref(true)

function clamp(value: unknown): number {
    const n = Number(value)
    if (!Number.isFinite(n)) {
        return 1
    }
    return Math.min(20, Math.max(1, Math.round(n)))
}

function confirm() {
    emit('insert', { rows: clamp(rows.value), cols: clamp(cols.value), withHeaderRow: withHeaderRow.value })
    open.value = false
}
</script>

<template>
    <Popover :open="open" @update:open="(v) => (open = v)">
        <PopoverTrigger as-child>
            <Button type="button" size="icon" class="size-8" variant="ghost" title="插入表格" @mousedown.prevent>
                <TableIcon class="size-4" />
            </Button>
        </PopoverTrigger>
        <PopoverContent class="w-56 space-y-3" align="start">
            <div class="grid grid-cols-2 gap-2">
                <label class="space-y-1 text-xs text-muted-foreground">
                    行数
                    <Input v-model="rows" type="number" min="1" max="20" />
                </label>
                <label class="space-y-1 text-xs text-muted-foreground">
                    列数
                    <Input v-model="cols" type="number" min="1" max="20" />
                </label>
            </div>
            <label class="flex items-center gap-2 text-sm">
                <Checkbox v-model="withHeaderRow" />
                含表头行
            </label>
            <Button type="button" size="sm" class="w-full" @click="confirm">插入</Button>
        </PopoverContent>
    </Popover>
</template>
