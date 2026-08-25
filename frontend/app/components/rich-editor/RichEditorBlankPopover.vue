<script setup lang="ts">
import { computed, ref, watch, nextTick, onBeforeUnmount } from 'vue'
import { Button } from '@/components/ui/button'
import { Slider } from '@/components/ui/slider'
import {
    BLANK_WIDTH_MIN_EM,
    BLANK_WIDTH_MAX_EM,
    clampBlankWidthEm,
} from './schemaExtensions'

const props = defineProps<{
    open: boolean
    widthEm: number
    anchorEl: HTMLElement | null
}>()

const emit = defineEmits<{
    update: [number]
    delete: []
    close: []
}>()

/** 长度预设：短 / 中 / 长（em）。 */
const PRESETS: { label: string; value: number }[] = [
    { label: '短', value: 2 },
    { label: '中', value: 4 },
    { label: '长', value: 8 },
]

const popoverRef = ref<HTMLElement | null>(null)
const posStyle = ref<Record<string, string>>({})
const local = ref(clampBlankWidthEm(props.widthEm))

const sliderValue = computed<number[]>({
    get: () => [local.value],
    set: (v) => setWidth(v[0] ?? local.value),
})

const teleportTarget = computed(
    () => props.anchorEl?.closest<HTMLElement>('[role="dialog"]') ?? 'body',
)

function setWidth(value: number) {
    const next = clampBlankWidthEm(value)
    if (next === local.value) {
        return
    }
    local.value = next
    emit('update', next)
}

function onNumberInput(event: Event) {
    const raw = Number((event.target as HTMLInputElement).value)
    if (Number.isFinite(raw)) {
        setWidth(raw)
    }
}

function position() {
    const el = props.anchorEl
    if (!el) {
        return
    }
    const rect = el.getBoundingClientRect()
    const width = 260
    let left = rect.left
    const maxLeft = window.innerWidth - width - 8
    if (left > maxLeft) {
        left = Math.max(8, maxLeft)
    }
    posStyle.value = {
        position: 'fixed',
        top: `${rect.bottom + 6}px`,
        left: `${left}px`,
        zIndex: '60',
    }
}

function onPointerDown(event: PointerEvent) {
    const target = event.target as Node
    if (popoverRef.value?.contains(target) || props.anchorEl?.contains(target)) {
        return
    }
    emit('close')
}

function onKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
        event.preventDefault()
        emit('close')
    }
}

watch(
    () => props.open,
    (v) => {
        if (v) {
            local.value = clampBlankWidthEm(props.widthEm)
            nextTick(() => {
                position()
                document.addEventListener('pointerdown', onPointerDown, true)
                document.addEventListener('keydown', onKeydown, true)
            })
        } else {
            document.removeEventListener('pointerdown', onPointerDown, true)
            document.removeEventListener('keydown', onKeydown, true)
        }
    },
)

watch(
    () => props.widthEm,
    (v) => {
        if (props.open) {
            local.value = clampBlankWidthEm(v)
        }
    },
)

onBeforeUnmount(() => {
    document.removeEventListener('pointerdown', onPointerDown, true)
    document.removeEventListener('keydown', onKeydown, true)
})
</script>

<template>
    <Teleport :to="teleportTarget">
        <div
            v-if="open"
            ref="popoverRef"
            class="rich-blank-popover w-[260px] rounded-md border border-border bg-popover p-3 shadow-md"
            :style="posStyle"
        >
            <div class="mb-2 flex items-center justify-between">
                <span class="text-xs text-muted-foreground">填空长度</span>
                <div class="flex items-center gap-1">
                    <input
                        type="number"
                        :min="BLANK_WIDTH_MIN_EM"
                        :max="BLANK_WIDTH_MAX_EM"
                        :value="local"
                        class="h-7 w-14 rounded-md border border-input bg-transparent px-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
                        @input="onNumberInput"
                    />
                    <span class="text-xs text-muted-foreground">em</span>
                </div>
            </div>

            <Slider
                :model-value="sliderValue"
                :min="BLANK_WIDTH_MIN_EM"
                :max="BLANK_WIDTH_MAX_EM"
                :step="1"
                class="my-2"
                @update:model-value="(v) => setWidth((v as number[])?.[0] ?? local)"
            />

            <div class="mt-2 flex items-center justify-between">
                <div class="flex gap-1">
                    <Button
                        v-for="preset in PRESETS"
                        :key="preset.value"
                        type="button"
                        :variant="local === preset.value ? 'default' : 'outline'"
                        size="sm"
                        class="h-7 px-2"
                        @pointerdown.prevent
                        @click="setWidth(preset.value)"
                    >
                        {{ preset.label }}
                    </Button>
                </div>
                <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    class="h-7 px-2 text-destructive hover:text-destructive"
                    @pointerdown.prevent
                    @click="emit('delete')"
                >
                    删除
                </Button>
            </div>
        </div>
    </Teleport>
</template>
