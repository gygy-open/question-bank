<script setup lang="ts">
import { Button } from '@/components/ui/button'
import AiMascot from '@/components/chat/AiMascot.vue'
import { useGlobalChat } from '@/composables/useGlobalChat'

const { t } = useI18n()
const chat = useGlobalChat()

const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform)
const shortcut = isMac ? '⌘I' : 'Ctrl+I'
</script>

<template>
  <div class="flex items-center gap-3 pl-1">
    <div class="h-5 w-px bg-border" aria-hidden="true" />
    <Button
      variant="ghost"
      size="sm"
      class="relative h-8 cursor-pointer gap-1.5 px-2 text-foreground sm:px-2.5"
      :class="chat.isOpen.value ? 'bg-accent text-accent-foreground' : ''"
      :aria-pressed="chat.isOpen.value"
      :aria-label="t('nav.aiAssistant')"
      :title="t('chat.panel.toggle', { shortcut })"
      @click="chat.toggle()"
    >
      <AiMascot :thinking="chat.loading.value" class="size-5 text-primary" />
      <span class="hidden sm:inline">{{ t('nav.aiAssistant') }}</span>
      <span
        v-if="chat.hasUnread.value && !chat.isOpen.value"
        class="absolute right-0.5 top-0.5 h-2 w-2 rounded-full bg-destructive"
      />
    </Button>
  </div>
</template>
