<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { Card, CardHeader, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  MoreVertical, Copy, Archive, ArchiveRestore, Trash2, FileText, BookmarkPlus, Check, X,
} from '@lucide/vue'
import { formatRelativeTime } from '@/lib/utils'
import type { Composition } from '~/types'

const props = defineProps<{
  item: Composition
  view: 'grid' | 'list'
}>()

const emit = defineEmits<{
  (e: 'open'): void
  (e: 'rename', title: string): void
  (e: 'duplicate'): void
  (e: 'save-as-template'): void
  (e: 'toggle-archive'): void
  (e: 'delete'): void
}>()

const isEditing = ref(false)
const editTitle = ref('')
const inputRef = ref<any>(null)

const startEdit = async () => {
  editTitle.value = props.item.title
  isEditing.value = true
  await nextTick()
  inputRef.value?.$el?.focus()
  inputRef.value?.$el?.select()
}

const cancelEdit = () => {
  isEditing.value = false
}

const saveEdit = () => {
  const title = editTitle.value.trim()
  isEditing.value = false
  if (!title || title === props.item.title) return
  emit('rename', title)
}

// Drives drag-to-move onto a folder in the sidebar tree.
const onDragStart = (e: DragEvent) => {
  e.dataTransfer?.setData('text/plain', String(props.item.id))
  if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move'
}
</script>

<template>
  <Card
    v-if="view === 'grid'"
    class="group hover:shadow-lg transition-shadow cursor-pointer"
    draggable="true"
    @dragstart="onDragStart"
    @click="!isEditing && emit('open')"
  >
    <CardHeader class="pb-3">
      <div class="flex items-start justify-between">
        <FileText class="h-5 w-5 text-muted-foreground" />
        <DropdownMenu>
          <DropdownMenuTrigger as-child @click.stop>
            <Button variant="ghost" size="icon" class="h-8 w-8 opacity-0 group-hover:opacity-100">
              <MoreVertical class="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" @click.stop>
            <DropdownMenuItem @click="startEdit">重命名</DropdownMenuItem>
            <DropdownMenuItem @click="emit('duplicate')">
              <Copy class="mr-2 h-4 w-4" /> 复制
            </DropdownMenuItem>
            <DropdownMenuItem @click="emit('save-as-template')">
              <BookmarkPlus class="mr-2 h-4 w-4" /> 另存为模板
            </DropdownMenuItem>
            <DropdownMenuItem @click="emit('toggle-archive')">
              <ArchiveRestore v-if="item.status === 'archived'" class="mr-2 h-4 w-4" />
              <Archive v-else class="mr-2 h-4 w-4" />
              {{ item.status === 'archived' ? '取消归档' : '归档' }}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem class="text-destructive" @click="emit('delete')">
              <Trash2 class="mr-2 h-4 w-4" /> 删除
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </CardHeader>
    <CardContent>
      <div v-if="isEditing" class="flex items-center gap-1" @click.stop>
        <Input ref="inputRef" v-model="editTitle" class="h-7 text-sm" @keyup.enter="saveEdit" @keyup.esc="cancelEdit" />
        <Button size="icon" variant="ghost" class="h-7 w-7 shrink-0 text-green-600" @click="saveEdit">
          <Check class="h-4 w-4" />
        </Button>
        <Button size="icon" variant="ghost" class="h-7 w-7 shrink-0 text-muted-foreground" @click="cancelEdit">
          <X class="h-4 w-4" />
        </Button>
      </div>
      <h3 v-else class="font-medium truncate">{{ item.title }}</h3>
      <div class="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
        <Badge variant="secondary">{{ item.block_count || 0 }} 项</Badge>
        <span>{{ formatRelativeTime(item.updated_at) }}</span>
      </div>
    </CardContent>
  </Card>

  <div
    v-else
    class="group flex items-center gap-3 px-3 py-2 rounded-md border hover:bg-muted/50 cursor-pointer"
    draggable="true"
    @dragstart="onDragStart"
    @click="!isEditing && emit('open')"
  >
    <FileText class="h-4 w-4 text-muted-foreground shrink-0" />

    <div v-if="isEditing" class="flex-1 flex items-center gap-1" @click.stop>
      <Input ref="inputRef" v-model="editTitle" class="h-7 text-sm" @keyup.enter="saveEdit" @keyup.esc="cancelEdit" />
      <Button size="icon" variant="ghost" class="h-7 w-7 shrink-0 text-green-600" @click="saveEdit">
        <Check class="h-4 w-4" />
      </Button>
      <Button size="icon" variant="ghost" class="h-7 w-7 shrink-0 text-muted-foreground" @click="cancelEdit">
        <X class="h-4 w-4" />
      </Button>
    </div>
    <span v-else class="flex-1 truncate font-medium">{{ item.title }}</span>

    <Badge variant="secondary" class="shrink-0">{{ item.block_count || 0 }} 项</Badge>
    <span class="text-xs text-muted-foreground shrink-0 w-20 text-right">{{ formatRelativeTime(item.updated_at) }}</span>

    <DropdownMenu>
      <DropdownMenuTrigger as-child @click.stop>
        <Button variant="ghost" size="icon" class="h-8 w-8 opacity-0 group-hover:opacity-100 shrink-0">
          <MoreVertical class="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" @click.stop>
        <DropdownMenuItem @click="startEdit">重命名</DropdownMenuItem>
        <DropdownMenuItem @click="emit('duplicate')">
          <Copy class="mr-2 h-4 w-4" /> 复制
        </DropdownMenuItem>
        <DropdownMenuItem @click="emit('save-as-template')">
          <BookmarkPlus class="mr-2 h-4 w-4" /> 另存为模板
        </DropdownMenuItem>
        <DropdownMenuItem @click="emit('toggle-archive')">
          <ArchiveRestore v-if="item.status === 'archived'" class="mr-2 h-4 w-4" />
          <Archive v-else class="mr-2 h-4 w-4" />
          {{ item.status === 'archived' ? '取消归档' : '归档' }}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem class="text-destructive" @click="emit('delete')">
          <Trash2 class="mr-2 h-4 w-4" /> 删除
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  </div>
</template>
