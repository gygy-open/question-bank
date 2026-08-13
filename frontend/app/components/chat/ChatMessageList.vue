<script setup lang="ts">
import { Bot, User, Loader2 } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import ChatMessage from '@/components/ChatMessage.vue'
import { useGlobalChat } from '@/composables/useGlobalChat'

const chat = useGlobalChat()
const scrollRoot = ref<HTMLElement | null>(null)

const scrollToBottom = async () => {
  await nextTick()
  const viewport = scrollRoot.value?.querySelector('[data-slot="scroll-area-viewport"]') as HTMLElement | null
  if (viewport) viewport.scrollTop = viewport.scrollHeight
}

// Follow the stream / new messages.
watch(
  () => chat.messages.value.length,
  () => scrollToBottom()
)
watch(
  () => chat.messages.value.length > 0 ? chat.messages.value[chat.messages.value.length - 1].content : '',
  () => scrollToBottom()
)

defineExpose({ scrollToBottom })
</script>

<template>
  <ScrollArea ref="scrollRoot" class="min-h-0 flex-1">
    <div class="flex flex-col gap-6 p-4">
      <div v-if="chat.hasMore.value" class="flex justify-center">
        <Button variant="ghost" size="sm" :disabled="chat.isLoadingMore.value" @click="chat.loadMore()">
          <Loader2 v-if="chat.isLoadingMore.value" class="mr-2 h-4 w-4 animate-spin" />
          {{ chat.isLoadingMore.value ? '加载中...' : '加载更多历史消息' }}
        </Button>
      </div>

      <div
        v-if="chat.messages.value.length === 0"
        class="flex h-48 flex-col items-center justify-center text-muted-foreground"
      >
        <Bot class="mb-3 h-10 w-10 opacity-20" />
        <p class="text-sm">开始与 AI 对话吧...</p>
      </div>

      <div v-for="(msg, index) in chat.messages.value" :key="index" class="flex items-start gap-2">
        <div v-if="chat.isSelectionMode.value" class="shrink-0 pt-2">
          <Checkbox
            :model-value="chat.selectedMessageIndices.value.has(index)"
            @update:model-value="chat.toggleMessageSelection(index)"
          />
        </div>

        <div :class="['flex flex-1 gap-2', msg.role === 'user' ? 'flex-row-reverse' : '']">
          <Avatar class="h-7 w-7">
            <AvatarFallback :class="msg.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted'">
              <User v-if="msg.role === 'user'" class="h-3.5 w-3.5" />
              <Bot v-else class="h-3.5 w-3.5" />
            </AvatarFallback>
          </Avatar>

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
      </div>
    </div>
  </ScrollArea>
</template>
