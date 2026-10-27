<script setup lang="ts">
import { MessageSquarePlus, CheckSquare, Maximize2, Minimize2, X, ArrowLeft } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import AiMascot from '@/components/chat/AiMascot.vue'
import { useGlobalChat } from '@/composables/useGlobalChat'

const { t } = useI18n()
const chat = useGlobalChat()

withDefaults(defineProps<{ showExpand?: boolean }>(), { showExpand: true })
</script>

<template>
  <header class="flex h-11 shrink-0 select-none items-center gap-1.5 px-2">
    <template v-if="chat.view.value === 'history'">
      <span class="ml-1 text-sm font-medium">{{ t('chat.header.history') }}</span>
    </template>
    <template v-else>
      <Button variant="ghost" size="icon" class="h-7 w-7 shrink-0 cursor-pointer" :title="t('chat.header.history')"
        @click="chat.view.value = 'history'">
        <ArrowLeft class="h-4 w-4" />
      </Button>
      <AiMascot :thinking="chat.loading.value" class="size-4 shrink-0 text-primary" />
      <span class="min-w-0 flex-1 truncate text-sm font-medium">{{ chat.currentTitle.value }}</span>
    </template>

    <div class="ml-auto flex items-center gap-0.5">
      <Button v-if="chat.view.value === 'chat'" variant="ghost" size="icon" class="h-7 w-7 cursor-pointer"
        :title="t('chat.newSession')" @click="chat.createNewSession()">
        <MessageSquarePlus class="h-4 w-4" />
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
