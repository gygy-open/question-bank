<script setup lang="ts">
import { Copy, X } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { useGlobalChat } from '@/composables/useGlobalChat'

const { t } = useI18n()
const chat = useGlobalChat()
</script>

<template>
  <div class="flex shrink-0 flex-wrap items-center justify-center gap-2 border-t bg-background p-3">
    <span class="text-sm font-medium">{{ t('chat.selection.count', { count: chat.selectedMessageIndices.value.size }) }}</span>
    <div class="h-4 w-px bg-border" />
    <Button size="sm" :disabled="chat.selectedMessageIndices.value.size === 0" @click="chat.copySelectedMessages()">
      <Copy class="mr-1.5 h-4 w-4" />
      {{ t('chat.copyMarkdown') }}
    </Button>
    <Button size="sm" variant="ghost" @click="chat.toggleSelectionMode()">
      <X class="mr-1.5 h-4 w-4" />
      {{ t('common.cancel') }}
    </Button>
  </div>
</template>
