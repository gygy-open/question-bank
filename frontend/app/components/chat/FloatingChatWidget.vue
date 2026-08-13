<script setup lang="ts">
import { useMediaQuery } from '@vueuse/core'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import PromptManager from '@/components/PromptManager.vue'
import ChatWidgetHeader from '@/components/chat/ChatWidgetHeader.vue'
import ChatHistoryPanel from '@/components/chat/ChatHistoryPanel.vue'
import ChatMessageList from '@/components/chat/ChatMessageList.vue'
import ChatComposer from '@/components/chat/ChatComposer.vue'
import ChatSelectionBar from '@/components/chat/ChatSelectionBar.vue'
import { useGlobalChat } from '@/composables/useGlobalChat'

const chat = useGlobalChat()
const isMobile = useMediaQuery('(max-width: 767px)')

const MIN_W = 320
const MIN_H = 420
const MARGIN = 24
const MINIMIZED_H = 44 // header-only height

// Resolve the effective top-left position. When unset (-1) or off-screen,
// dock to the bottom-right of the viewport.
const resolvedPos = computed(() => {
  if (typeof window === 'undefined') return { x: 0, y: 0 }
  const width = chat.size.value.width
  const height = chat.isMinimized.value ? MINIMIZED_H : chat.size.value.height
  let { x, y } = chat.position.value
  if (x < 0 || y < 0) {
    x = window.innerWidth - width - MARGIN
    y = window.innerHeight - height - MARGIN
  }
  x = Math.max(0, Math.min(x, window.innerWidth - width))
  y = Math.max(0, Math.min(y, window.innerHeight - height))
  return { x, y }
})

const panelStyle = computed(() => {
  if (isMobile.value) {
    return { inset: '0', width: '100%', height: '100%', borderRadius: '0' }
  }
  return {
    left: `${resolvedPos.value.x}px`,
    top: `${resolvedPos.value.y}px`,
    width: `${chat.size.value.width}px`,
    height: chat.isMinimized.value ? 'auto' : `${chat.size.value.height}px`,
  }
})

// --- Drag ---
let dragStart = { px: 0, py: 0, x: 0, y: 0 }
const onDragStart = (e: PointerEvent) => {
  if (isMobile.value) return
  const target = e.target as HTMLElement
  // Ignore drags that start on interactive controls inside the header.
  if (target.closest('button, input')) return
  const handle = target.closest('[data-chat-drag-handle]')
  if (!handle) return
  dragStart = { px: e.clientX, py: e.clientY, x: resolvedPos.value.x, y: resolvedPos.value.y }
  window.addEventListener('pointermove', onDragMove)
  window.addEventListener('pointerup', onDragEnd)
}
const onDragMove = (e: PointerEvent) => {
  const dx = e.clientX - dragStart.px
  const dy = e.clientY - dragStart.py
  const w = chat.size.value.width
  const h = chat.isMinimized.value ? MINIMIZED_H : chat.size.value.height
  chat.position.value = {
    x: Math.max(0, Math.min(dragStart.x + dx, window.innerWidth - w)),
    y: Math.max(0, Math.min(dragStart.y + dy, window.innerHeight - h)),
  }
}
const onDragEnd = () => {
  window.removeEventListener('pointermove', onDragMove)
  window.removeEventListener('pointerup', onDragEnd)
}

// --- Resize (bottom-right handle) ---
let resizeStart = { px: 0, py: 0, w: 0, h: 0 }
const onResizeStart = (e: PointerEvent) => {
  if (isMobile.value) return
  e.stopPropagation()
  resizeStart = { px: e.clientX, py: e.clientY, w: chat.size.value.width, h: chat.size.value.height }
  window.addEventListener('pointermove', onResizeMove)
  window.addEventListener('pointerup', onResizeEnd)
}
const onResizeMove = (e: PointerEvent) => {
  const maxW = window.innerWidth * 0.9
  const maxH = window.innerHeight * 0.9
  chat.size.value = {
    width: Math.max(MIN_W, Math.min(resizeStart.w + (e.clientX - resizeStart.px), maxW)),
    height: Math.max(MIN_H, Math.min(resizeStart.h + (e.clientY - resizeStart.py), maxH)),
  }
}
const onResizeEnd = () => {
  window.removeEventListener('pointermove', onResizeMove)
  window.removeEventListener('pointerup', onResizeEnd)
}

const onKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Escape') {
    const target = e.target as HTMLElement
    // Let inner editable controls handle Esc first (e.g. rename input).
    if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') return
    chat.close()
  }
}
</script>

<template>
  <Teleport to="body">
    <div
      v-show="chat.isOpen.value"
      class="fixed z-40 flex flex-col overflow-hidden rounded-lg border bg-background shadow-2xl"
      :style="panelStyle"
      role="dialog"
      aria-label="AI 助手"
      @keydown="onKeydown"
      @pointerdown="onDragStart"
    >
      <ChatWidgetHeader />

      <div v-show="!chat.isMinimized.value" class="flex min-h-0 flex-1 flex-col">
        <ChatHistoryPanel v-if="chat.view.value === 'history'" class="min-h-0 flex-1" />
        <template v-else>
          <ChatMessageList />
          <ChatSelectionBar v-if="chat.isSelectionMode.value" />
          <ChatComposer v-else />
        </template>
      </div>

      <!-- Resize handle (desktop only) -->
      <div
        v-if="!isMobile && !chat.isMinimized.value"
        class="absolute bottom-0 right-0 h-4 w-4 cursor-nwse-resize"
        @pointerdown="onResizeStart"
      >
        <svg viewBox="0 0 10 10" class="h-full w-full text-muted-foreground/50">
          <path d="M9 1 L1 9 M9 5 L5 9" stroke="currentColor" stroke-width="1" fill="none" />
        </svg>
      </div>
    </div>

    <!-- Image preview -->
    <Dialog v-model:open="chat.isPreviewOpen.value">
      <DialogContent class="w-full max-w-4xl overflow-hidden border-none bg-transparent p-0 shadow-none sm:max-w-4xl">
        <div class="relative flex h-full w-full items-center justify-center" @click="chat.isPreviewOpen.value = false">
          <img
            v-if="chat.previewImage.value"
            :src="chat.previewImage.value"
            class="max-h-[90vh] max-w-full rounded-md object-contain"
          />
        </div>
      </DialogContent>
    </Dialog>

    <PromptManager v-model:open="chat.isPromptManagerOpen.value" @select="chat.handlePromptSelect" />
  </Teleport>
</template>
