<script setup lang="ts">
import { Loader2 } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import ChatMessage from '@/components/ChatMessage.vue'
import AiMascot from '@/components/chat/AiMascot.vue'
import {
  MessageScroller,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerProvider,
  MessageScrollerViewport,
} from '@/components/ui/message-scroller'
import { useGlobalChat } from '@/composables/useGlobalChat'

const { t } = useI18n()
const chat = useGlobalChat()
</script>

<template>
  <MessageScrollerProvider :auto-scroll="true" default-scroll-position="end">
    <MessageScroller class="min-h-0 flex-1">
      <MessageScrollerViewport
        class="[scrollbar-color:transparent_transparent] [scrollbar-gutter:stable] [scrollbar-width:thin] hover:[scrollbar-color:color-mix(in_oklab,var(--muted-foreground)_40%,transparent)_transparent]"
      >
        <div v-if="chat.hasMore.value" class="flex justify-center px-4 pt-4">
          <Button variant="ghost" size="sm" :disabled="chat.isLoadingMore.value" @click="chat.loadMore()">
            <Loader2 v-if="chat.isLoadingMore.value" class="mr-2 h-4 w-4 animate-spin" />
            {{ chat.isLoadingMore.value ? t('common.loading') : t('chat.messages.loadMoreHistory') }}
          </Button>
        </div>

        <div
          v-if="chat.messages.value.length === 0"
          class="flex h-48 flex-col items-center justify-center text-muted-foreground"
        >
          <AiMascot class="mb-3 size-12 text-primary/60" />
          <p class="text-sm">{{ t('chat.messages.empty') }}</p>
        </div>

        <MessageScrollerContent class="gap-6 p-4">
          <MessageScrollerItem
            v-for="(msg, index) in chat.messages.value"
            :key="msg.uiId"
            :message-id="msg.uiId"
            :scroll-anchor="msg.role === 'user'"
            class="flex items-start gap-2"
          >
            <div v-if="chat.isSelectionMode.value" class="shrink-0 pt-0.5">
              <Checkbox
                :model-value="chat.selectedMessageIndices.value.has(index)"
                @update:model-value="chat.toggleMessageSelection(index)"
              />
            </div>

            <div :class="['flex min-w-0 flex-1', msg.role === 'user' ? 'justify-end' : '']">
              <ChatMessage
                :id="msg.id"
                :role="msg.role as any"
                :content="msg.content"
                :images="msg.images"
                :loading="chat.loading.value && index === chat.messages.value.length - 1"
                :actions="msg.actions"
                :proposal="msg.proposal"
                @preview-image="chat.openPreview"
                @update="chat.handleUpdateMessage"
                @delete="chat.handleDeleteMessage"
              />
            </div>
          </MessageScrollerItem>
        </MessageScrollerContent>
      </MessageScrollerViewport>
    </MessageScroller>
  </MessageScrollerProvider>
</template>
