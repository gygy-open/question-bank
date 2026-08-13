<script setup lang="ts">
import { Bot, History, MessageSquarePlus, CheckSquare, Minus, Maximize2, X, RotateCcw, ArrowLeft } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { useGlobalChat } from '@/composables/useGlobalChat'

const chat = useGlobalChat()
</script>

<template>
  <header
    data-chat-drag-handle
    class="flex h-11 shrink-0 cursor-move select-none items-center gap-1.5 border-b bg-muted/40 px-2"
  >
    <template v-if="chat.view.value === 'history'">
      <Button variant="ghost" size="icon" class="h-7 w-7 cursor-pointer" title="返回聊天"
        @click="chat.view.value = 'chat'">
        <ArrowLeft class="h-4 w-4" />
      </Button>
      <span class="text-sm font-medium">历史对话</span>
    </template>
    <template v-else>
      <Bot class="ml-1 h-4 w-4 shrink-0 text-primary" />
      <span
        class="min-w-0 flex-1 truncate text-sm font-medium"
        :class="chat.isMinimized.value ? 'cursor-pointer' : ''"
        @click="chat.isMinimized.value && chat.restore()"
      >{{ chat.currentTitle.value }}</span>
    </template>

    <div class="ml-auto flex items-center gap-0.5">
      <Button v-if="chat.view.value === 'chat' && !chat.isMinimized.value" variant="ghost" size="icon" class="h-7 w-7 cursor-pointer"
        title="新对话" @click="chat.createNewSession()">
        <MessageSquarePlus class="h-4 w-4" />
      </Button>
      <Button v-if="chat.view.value === 'chat' && !chat.isMinimized.value" variant="ghost" size="icon"
        class="h-7 w-7 cursor-pointer" title="历史对话"
        @click="chat.view.value = 'history'">
        <History class="h-4 w-4" />
      </Button>
      <Button v-if="chat.view.value === 'chat' && !chat.isMinimized.value && chat.messages.value.length > 0" variant="ghost" size="icon" class="h-7 w-7 cursor-pointer"
        :class="chat.isSelectionMode.value ? 'bg-accent' : ''" title="多选消息"
        @click="chat.toggleSelectionMode()">
        <CheckSquare class="h-4 w-4" />
      </Button>
      <Button v-if="!chat.isMinimized.value" variant="ghost" size="icon" class="h-7 w-7 cursor-pointer" title="重置位置与大小"
        @click="chat.resetGeometry()">
        <RotateCcw class="h-4 w-4" />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        class="h-7 w-7 cursor-pointer"
        :title="chat.isMinimized.value ? '展开' : '最小化'"
        @click="chat.isMinimized.value ? chat.restore() : chat.minimize()"
      >
        <Maximize2 v-if="chat.isMinimized.value" class="h-4 w-4" />
        <Minus v-else class="h-4 w-4" />
      </Button>
      <Button variant="ghost" size="icon" class="h-7 w-7 cursor-pointer" title="关闭" @click="chat.close()">
        <X class="h-4 w-4" />
      </Button>
    </div>
  </header>
</template>
