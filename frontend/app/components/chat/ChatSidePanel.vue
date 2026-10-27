<script setup lang="ts">
import { useEventListener, useMediaQuery, useWindowSize } from '@vueuse/core'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { Sheet, SheetContent, SheetTitle } from '@/components/ui/sheet'
import { useSidebar } from '@/components/ui/sidebar'
import PromptManager from '@/components/PromptManager.vue'
import ChatWidgetHeader from '@/components/chat/ChatWidgetHeader.vue'
import ChatHistoryPanel from '@/components/chat/ChatHistoryPanel.vue'
import ChatMessageList from '@/components/chat/ChatMessageList.vue'
import ChatComposer from '@/components/chat/ChatComposer.vue'
import ChatSelectionBar from '@/components/chat/ChatSelectionBar.vue'
import { CHAT_PANEL_DEFAULT_WIDTH, useGlobalChat } from '@/composables/useGlobalChat'

const { t } = useI18n()
const chat = useGlobalChat()
const sidebar = useSidebar()
const isMobile = useMediaQuery('(max-width: 767px)')
const isMidScreen = useMediaQuery('(min-width: 768px) and (max-width: 1279px)')
const { width: windowWidth } = useWindowSize()

const MIN_W = 320
const maxWidth = computed(() => Math.max(MIN_W, Math.min(720, Math.floor(windowWidth.value * 0.6))))
const clampWidth = (w: number) => Math.max(MIN_W, Math.min(w, maxWidth.value))
const effectiveWidth = computed(() => clampWidth(chat.panelWidth.value))

const panelEl = ref<HTMLElement | null>(null)

// --- Resize from the left edge ---
const isResizing = ref(false)
let resizeStart = { x: 0, w: 0 }
const onResizeMove = (e: PointerEvent) => {
  chat.panelWidth.value = clampWidth(resizeStart.w + (resizeStart.x - e.clientX))
}
const onResizeEnd = () => {
  isResizing.value = false
  document.body.style.removeProperty('cursor')
  document.body.style.removeProperty('user-select')
  window.removeEventListener('pointermove', onResizeMove)
  window.removeEventListener('pointerup', onResizeEnd)
}
const onResizeStart = (e: PointerEvent) => {
  e.preventDefault()
  isResizing.value = true
  resizeStart = { x: e.clientX, w: effectiveWidth.value }
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  window.addEventListener('pointermove', onResizeMove)
  window.addEventListener('pointerup', onResizeEnd)
}
const resetWidth = () => {
  chat.panelWidth.value = CHAT_PANEL_DEFAULT_WIDTH
}
onBeforeUnmount(onResizeEnd)

// Expanded mode overlays the content area, leaving the left sidebar visible.
const panelStyle = computed(() => {
  if (chat.isExpanded.value) {
    return {
      left: sidebar.open.value ? 'var(--sidebar-width)' : 'var(--sidebar-width-icon)',
    }
  }
  return { width: `${effectiveWidth.value}px` }
})

// --- Mid-size screens: collapse the left sidebar while the panel is open ---
// Mutates `open` directly (not setOpen) so the user's persisted preference
// in the sidebar cookie is left untouched.
let collapsedByPanel = false
watch(
  [chat.isOpen, isMidScreen],
  ([isOpen, mid]) => {
    if (isOpen && mid) {
      if (sidebar.open.value) {
        sidebar.open.value = false
        collapsedByPanel = true
      }
    } else if (collapsedByPanel) {
      collapsedByPanel = false
      if (!sidebar.open.value) sidebar.open.value = true
    }
  },
  { immediate: true },
)
// If the user re-opens the sidebar manually, don't fight them later.
watch(sidebar.open, (open) => {
  if (open) collapsedByPanel = false
})

const focusComposer = () => {
  nextTick(() => {
    const root: ParentNode = isMobile.value ? document : (panelEl.value ?? document)
    root.querySelector<HTMLTextAreaElement>('[data-chat-input]')?.focus()
  })
}
watch(chat.isOpen, (open) => {
  if (open) focusComposer()
})

const onKeydown = (e: KeyboardEvent) => {
  if (e.key !== 'Escape') return
  const target = e.target as HTMLElement
  // Inner inputs (e.g. session rename) handle Esc themselves.
  if (target.tagName === 'INPUT') return
  if (target.tagName === 'TEXTAREA') {
    target.blur()
    return
  }
  if (chat.isExpanded.value) chat.isExpanded.value = false
}

// The panel state is persisted; restore models/sessions when reloading with it open.
onMounted(() => {
  if (chat.isOpen.value) chat.open()
})

useEventListener('keydown', (e: KeyboardEvent) => {
  if (e.key.toLowerCase() !== 'i' || !(e.ctrlKey || e.metaKey) || e.altKey || e.shiftKey) return
  const target = e.target as HTMLElement | null
  // Keep Ctrl/⌘+I (italic) working inside rich-text and math editors.
  if (target?.closest('[contenteditable="true"], .ProseMirror, math-field')) return
  e.preventDefault()
  chat.toggle()
})

const mobileOpen = computed({
  get: () => chat.isOpen.value,
  set: (v: boolean) => (v ? chat.open() : chat.close()),
})
</script>

<template>
  <!-- Desktop: docked panel in the layout flow (pushes content, does not cover it) -->
  <aside
    v-if="!isMobile"
    v-show="chat.isOpen.value"
    ref="panelEl"
    class="flex h-svh shrink-0 flex-col border-l bg-background"
    :class="chat.isExpanded.value ? 'fixed inset-y-0 right-0 z-30 shadow-2xl' : 'sticky top-0'"
    :style="panelStyle"
    :aria-label="t('nav.aiAssistant')"
    @keydown="onKeydown"
  >
    <div
      v-if="!chat.isExpanded.value"
      role="separator"
      aria-orientation="vertical"
      :aria-label="t('chat.panel.resize')"
      :title="t('chat.panel.resize')"
      class="absolute inset-y-0 -left-1 z-10 w-2 cursor-col-resize after:absolute after:inset-y-0 after:left-1/2 after:w-px after:-translate-x-1/2 after:transition-colors hover:after:bg-primary/60"
      :class="isResizing ? 'after:bg-primary' : ''"
      @pointerdown="onResizeStart"
      @dblclick="resetWidth"
    />
    <ChatWidgetHeader />
    <div class="flex min-h-0 flex-1 flex-col">
      <ChatHistoryPanel v-if="chat.view.value === 'history'" class="min-h-0 flex-1" />
      <template v-else>
        <ChatMessageList />
        <ChatSelectionBar v-if="chat.isSelectionMode.value" />
        <ChatComposer v-else />
      </template>
    </div>
  </aside>

  <!-- Mobile: full-screen sheet from the right -->
  <Sheet v-else v-model:open="mobileOpen">
    <SheetContent
      side="right"
      class="w-full gap-0 p-0 sm:max-w-none [&>button.absolute]:hidden"
      :aria-describedby="undefined"
      @keydown="onKeydown"
    >
      <SheetTitle class="sr-only">{{ t('nav.aiAssistant') }}</SheetTitle>
      <ChatWidgetHeader :show-expand="false" />
      <div class="flex min-h-0 flex-1 flex-col">
        <ChatHistoryPanel v-if="chat.view.value === 'history'" class="min-h-0 flex-1" />
        <template v-else>
          <ChatMessageList />
          <ChatSelectionBar v-if="chat.isSelectionMode.value" />
          <ChatComposer v-else />
        </template>
      </div>
    </SheetContent>
  </Sheet>

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
</template>
