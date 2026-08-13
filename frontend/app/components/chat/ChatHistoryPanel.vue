<script setup lang="ts">
import { Plus, MessageSquare, Pencil, Trash2, Loader2 } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { useGlobalChat } from '@/composables/useGlobalChat'

const chat = useGlobalChat()

const selectSession = (id: string) => {
  chat.loadSession(id)
}
</script>

<template>
  <div class="flex h-full flex-col">
    <div class="border-b p-2">
      <Button class="w-full justify-start gap-2" size="sm" @click="chat.createNewSession()">
        <Plus class="h-4 w-4" />
        新对话
      </Button>
    </div>
    <ScrollArea class="min-h-0 flex-1">
      <div class="flex flex-col gap-1 p-2">
        <div
          v-for="session in chat.sessions.value"
          :key="session.id"
          :class="[
            'group flex cursor-pointer items-center gap-2 rounded-md p-2 text-sm transition-colors hover:bg-accent/50',
            chat.currentSessionId.value === session.id ? 'bg-accent text-accent-foreground' : 'text-muted-foreground',
          ]"
          @click="selectSession(session.id)"
        >
          <MessageSquare class="h-4 w-4 shrink-0" />

          <input
            v-if="chat.editingSessionId.value === session.id"
            v-model="chat.editTitle.value"
            class="h-6 w-full flex-1 rounded border border-input bg-background px-2 py-0.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            autofocus
            @click.stop
            @keydown.enter="chat.saveTitle()"
            @keydown.esc.stop="chat.cancelEditing()"
            @blur="chat.saveTitle()"
          />
          <span v-else class="flex-1 truncate">{{ session.title || '新对话' }}</span>

          <div
            v-if="chat.editingSessionId.value !== session.id"
            class="flex items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100"
          >
            <button
              class="rounded-md p-1.5 transition-colors hover:bg-background hover:text-foreground"
              title="重命名"
              @click="(e) => chat.startEditing(session, e)"
            >
              <Pencil class="h-3 w-3" />
            </button>
            <button
              class="rounded-md p-1.5 transition-colors hover:bg-destructive/10 hover:text-destructive"
              title="删除"
              @click="(e) => chat.deleteSession(session.id, e)"
            >
              <Trash2 class="h-3 w-3" />
            </button>
          </div>
        </div>

        <div v-if="chat.sessions.value.length === 0" class="py-8 text-center text-sm text-muted-foreground">
          暂无对话
        </div>

        <Button
          v-if="chat.hasMoreSessions.value"
          variant="ghost"
          size="sm"
          class="mt-2 w-full text-xs"
          :disabled="chat.isLoadingMoreSessions.value"
          @click="chat.fetchSessions(true)"
        >
          <Loader2 v-if="chat.isLoadingMoreSessions.value" class="mr-2 h-3 w-3 animate-spin" />
          {{ chat.isLoadingMoreSessions.value ? '加载中...' : '加载更多' }}
        </Button>
      </div>
    </ScrollArea>
  </div>
</template>
