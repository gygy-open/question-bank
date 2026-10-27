<script setup lang="ts">
import { Sparkles } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { useGlobalChat } from '@/composables/useGlobalChat'

const { t } = useI18n()
const chat = useGlobalChat()

const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)
const shortcut = isMac ? '⌘I' : 'Ctrl+I'
</script>

<template>
  <div class="flex items-center gap-2">
    <div class="h-5 w-px bg-border" aria-hidden="true" />
    <Button
      variant="ghost"
      size="icon"
      class="relative h-8 w-8 cursor-pointer"
      :class="chat.isOpen.value ? 'bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary' : ''"
      :aria-pressed="chat.isOpen.value"
      :aria-label="t('nav.aiAssistant')"
      :title="t('chat.panel.toggle', { shortcut })"
      @click="chat.toggle()"
    >
      <Sparkles class="h-4 w-4" />
      <span
        v-if="chat.hasUnread.value && !chat.isOpen.value"
        class="absolute right-1 top-1 h-2 w-2 rounded-full bg-destructive"
        :class="chat.loading.value ? 'animate-pulse' : ''"
      />
    </Button>
  </div>
</template>
