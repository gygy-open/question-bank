<script setup lang="ts">
import { computed, ref, watch, nextTick } from 'vue'
import { MathfieldElement } from 'mathlive'
import 'mathlive/static.css'
import { Button } from '@/components/ui/button'

// 关闭 MathLive 默认音效，避免请求并不存在的 .wav 资源（控制台 404）。
if (typeof window !== 'undefined') {
    MathfieldElement.soundsDirectory = null
}

const props = defineProps<{
    open: boolean
    latex: string
    displayMode: boolean
    anchorEl: HTMLElement | null
    canDelete: boolean
}>()

const emit = defineEmits<{
    submit: [string]
    cancel: []
    delete: []
}>()

const mathfieldRef = ref<HTMLElement | null>(null)
const posStyle = ref<Record<string, string>>({})
const teleportTarget = computed(
    () => props.anchorEl?.closest<HTMLElement>('[role="dialog"]') ?? 'body',
)

function position() {
    const el = props.anchorEl
    if (!el) {
        return
    }
    const rect = el.getBoundingClientRect()
    const width = 320
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

function currentValue(): string {
    const mf = mathfieldRef.value as any
    return mf ? String(mf.value ?? '').trim() : ''
}

function setup() {
    const mf = mathfieldRef.value as any
    if (!mf) {
        return
    }
    mf.value = props.latex
    mf.addEventListener('keydown', onKeydown)
    setTimeout(() => mf.focus(), 0)
}

function onKeydown(event: KeyboardEvent) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault()
        emit('submit', currentValue())
    } else if (event.key === 'Escape') {
        event.preventDefault()
        event.stopPropagation()
        emit('cancel')
    }
}

watch(
    () => props.open,
    (v) => {
        if (v) {
            nextTick(() => {
                position()
                setup()
            })
        }
    },
)
</script>

<template>
    <Teleport :to="teleportTarget">
        <div
            v-if="open"
            class="rich-math-popover w-80 rounded-md border border-border bg-popover p-2 shadow-md"
            :style="posStyle"
        >
            <math-field ref="mathfieldRef" class="block w-full" />
            <div class="mt-2 flex items-center justify-between">
                <Button
                    v-if="canDelete"
                    type="button"
                    variant="destructive"
                    size="sm"
                    @pointerdown.prevent
                    @click="emit('delete')"
                >
                    删除
                </Button>
                <span v-else />
                <div class="flex gap-2">
                    <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        @pointerdown.prevent
                        @click="emit('cancel')"
                    >
                        取消
                    </Button>
                    <Button type="button" size="sm" @pointerdown.prevent @click="emit('submit', currentValue())">
                        完成
                    </Button>
                </div>
            </div>
        </div>
    </Teleport>
</template>

<style>
.rich-math-popover math-field {
    min-height: 40px;
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 4px 6px;
    background: var(--background);
    font-size: 1.1em;
}
.rich-math-popover math-field:focus-within {
    outline: 2px solid var(--ring);
    outline-offset: 1px;
}
.rich-math-popover math-field::part(menu-toggle) {
    display: none;
}
</style>
