<script setup lang="ts">
import { Bot, History, MessageSquarePlus, CheckSquare, Maximize2, Minimize2, X, ArrowLeft } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { useGlobalChat } from '@/composables/useGlobalChat'

const { t } = useI18n()
const chat = useGlobalChat()

withDefaults(defineProps<{ showExpand?: boolean }>(), { showExpand: true })
</script>

<template>
  <header class="flex h-11 shrink-0 select-none items-center gap-1.5 border-b bg-muted/40 px-2">
    <template v-if="chat.view.value === 'history'">
      <Button variant="ghost" size="icon" class="h-7 w-7 cursor-pointer" :title="t('chat.header.backToChat')"
        @click="chat.view.value = 'chat'">
        <ArrowLeft class="h-4 w-4" />
      </Button>
      <span class="text-sm font-medium">{{ t('chat.header.history') }}</span>
    </template>
    <template v-else>
      <Bot class="ml-1 h-4 w-4 shrink-0 text-primary" />
      <span class="min-w-0 flex-1 truncate text-sm font-medium">{{ chat.currentTitle.value }}</span>
    </template>

    <div class="ml-auto flex items-center gap-0.5">
      <Button v-if="chat.view.value === 'chat'" variant="ghost" size="icon" class="h-7 w-7 cursor-pointer"
        :title="t('chat.newSession')" @click="chat.createNewSession()">
        <MessageSquarePlus class="h-4 w-4" />
      </Button>
      <Button v-if="chat.view.value === 'chat'" variant="ghost" size="icon"
        class="h-7 w-7 cursor-pointer" :title="t('chat.header.history')"
        @click="chat.view.value = 'history'">
        <History class="h-4 w-4" />
      </Button>
      <Button v-if="chat.view.value === 'chat' && chat.messages.value.length > 0" variant="ghost" size="icon" class="h-7 w-7 cursor-pointer"
        :class="chat.isSelectionMode.value ? 'bg-accent' : ''" :title="t('chat.header.multiSelect')"
        @click="chat.toggleSelectionMode()">
        <CheckSquare class="h-4 w-4" />
      </Button>
      <Button
        v-if="showExpand"
        variant="ghost"
        size="icon"
        class="h-7 w-7 cursor-pointer"
        :title="chat.isExpanded.value ? t('chat.header.collapse') : t('chat.header.expand')"
        @click="chat.toggleExpanded()"
      >
        <Minimize2 v-if="chat.isExpanded.value" class="h-4 w-4" />
        <Maximize2 v-else class="h-4 w-4" />
      </Button>
      <Button variant="ghost" size="icon" class="h-7 w-7 cursor-pointer" :title="t('common.close')" @click="chat.close()">
        <X class="h-4 w-4" />
      </Button>
    </div>
  </header>
</template>
