<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import { ChevronRight, ChevronDown, FilePlus2, MoreHorizontal, FolderPlus, Pencil, Trash2, Folder as FolderIcon, Check, X } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import type { Folder } from '~/types'

interface FolderNode extends Folder {
  children: FolderNode[]
}

const props = defineProps<{
  folder: FolderNode
  level?: number
  activeFolderId: number | 'all'
}>()

const emit = defineEmits<{
  (e: 'select', id: number): void
  (e: 'rename', id: number, name: string): void
  (e: 'delete', id: number): void
  (e: 'create', parentId: number, name: string): void
  (e: 'create-item', folderId: number): void
  (e: 'drop-item', folderId: number, itemId: number): void
}>()

const showDeleteDialog = ref(false)

const isOpen = ref(true)
const hasChildren = computed(() => props.folder.children.length > 0)

const toggleOpen = () => {
  if (hasChildren.value) isOpen.value = !isOpen.value
}

// Drop target for dragging a composition card onto this folder to move it.
const isDragOver = ref(false)
const onDragOver = (e: DragEvent) => {
  e.preventDefault()
  isDragOver.value = true
}
const onDragLeave = () => {
  isDragOver.value = false
}
const onDrop = (e: DragEvent) => {
  e.preventDefault()
  isDragOver.value = false
  const itemId = Number(e.dataTransfer?.getData('text/plain'))
  if (itemId) emit('drop-item', props.folder.id, itemId)
}

// --- Inline rename ---
const isEditing = ref(false)
const editName = ref('')
const editInputRef = ref<any>(null)

const startEdit = async () => {
  editName.value = props.folder.name
  isEditing.value = true
  await nextTick()
  editInputRef.value?.$el?.focus()
  editInputRef.value?.$el?.select()
}

const cancelEdit = () => {
  isEditing.value = false
}

const saveEdit = () => {
  const name = editName.value.trim()
  isEditing.value = false
  if (!name || name === props.folder.name) return
  emit('rename', props.folder.id, name)
}

// --- Inline create (subfolder) ---
const isCreating = ref(false)
const newName = ref('')
const createInputRef = ref<any>(null)

const startCreate = async () => {
  newName.value = ''
  isCreating.value = true
  isOpen.value = true
  await nextTick()
  createInputRef.value?.$el?.focus()
}

const cancelCreate = () => {
  isCreating.value = false
}

const saveCreate = () => {
  const name = newName.value.trim()
  isCreating.value = false
  if (!name) return
  emit('create', props.folder.id, name)
}
</script>

<template>
  <div>
    <div
      class="group flex items-center gap-1 px-2 py-1.5 rounded-md text-sm cursor-pointer border border-transparent"
      :class="isDragOver ? 'bg-primary/10 border-primary/50' : (activeFolderId === folder.id ? 'bg-primary/10 text-primary' : 'hover:bg-muted')"
      :style="{ paddingLeft: `${(level || 0) * 1.25 + 0.5}rem` }"
      @click="!isEditing && $emit('select', folder.id)"
      @dragover="onDragOver"
      @dragleave="onDragLeave"
      @drop="onDrop"
    >
      <button
        class="p-0.5 rounded-sm hover:bg-muted-foreground/10 text-muted-foreground shrink-0"
        :class="{ invisible: !hasChildren }"
        @click.stop="toggleOpen"
      >
        <ChevronDown v-if="isOpen" class="h-3.5 w-3.5" />
        <ChevronRight v-else class="h-3.5 w-3.5" />
      </button>

      <FolderIcon class="h-4 w-4 shrink-0" />

      <template v-if="isEditing">
        <Input
          ref="editInputRef"
          v-model="editName"
          class="h-6 text-sm flex-1"
          @click.stop
          @keyup.enter="saveEdit"
          @keyup.esc="cancelEdit"
        />
        <Button size="icon" variant="ghost" class="h-6 w-6 shrink-0 text-green-600" @click.stop="saveEdit">
          <Check class="h-3.5 w-3.5" />
        </Button>
        <Button size="icon" variant="ghost" class="h-6 w-6 shrink-0 text-muted-foreground" @click.stop="cancelEdit">
          <X class="h-3.5 w-3.5" />
        </Button>
      </template>
      <span v-else class="flex-1 truncate">{{ folder.name }}</span>

      <div v-if="!isEditing" class="flex items-center gap-0.5 shrink-0 opacity-0 group-hover:opacity-100">
        <Button size="icon" variant="ghost" class="h-6 w-6" title="新建教研资产" @click.stop="emit('create-item', folder.id)">
          <FilePlus2 class="h-3.5 w-3.5" />
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger as-child>
            <Button size="icon" variant="ghost" class="h-6 w-6" title="更多操作" @click.stop>
              <MoreHorizontal class="h-3.5 w-3.5" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" @click.stop>
            <DropdownMenuItem @click="startCreate">
              <FolderPlus class="mr-2 h-4 w-4" /> 新建子文件夹
            </DropdownMenuItem>
            <DropdownMenuItem @click="startEdit">
              <Pencil class="mr-2 h-4 w-4" /> 重命名
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem class="text-destructive" @click="showDeleteDialog = true">
              <Trash2 class="mr-2 h-4 w-4" /> 删除
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>

    <AlertDialog v-model:open="showDeleteDialog">
      <AlertDialogContent @click.stop>
        <AlertDialogHeader>
          <AlertDialogTitle>删除「{{ folder.name }}」？</AlertDialogTitle>
          <AlertDialogDescription>
            {{ hasChildren ? '该文件夹下的子文件夹和全部教研资产将被一并删除，且无法恢复。' : '文件夹内的教研资产将被一并删除，且无法恢复。' }}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>取消</AlertDialogCancel>
          <AlertDialogAction class="bg-destructive text-destructive-foreground hover:bg-destructive/90" @click="emit('delete', folder.id)">
            确认删除
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>

    <div v-if="isOpen">
      <LibraryFolderTreeItem
        v-for="child in folder.children"
        :key="child.id"
        :folder="child"
        :level="(level || 0) + 1"
        :active-folder-id="activeFolderId"
        @select="(id) => emit('select', id)"
        @rename="(id, name) => emit('rename', id, name)"
        @delete="(id) => emit('delete', id)"
        @create="(parentId, name) => emit('create', parentId, name)"
        @create-item="(folderId) => emit('create-item', folderId)"
        @drop-item="(folderId, itemId) => emit('drop-item', folderId, itemId)"
      />

      <div
        v-if="isCreating"
        class="flex items-center gap-1 px-2 py-1.5"
        :style="{ paddingLeft: `${((level || 0) + 1) * 1.25 + 0.5}rem` }"
      >
        <div class="w-4 shrink-0" />
        <FolderIcon class="h-4 w-4 shrink-0 text-muted-foreground" />
        <Input
          ref="createInputRef"
          v-model="newName"
          class="h-6 text-sm flex-1"
          placeholder="新建子文件夹"
          @keyup.enter="saveCreate"
          @keyup.esc="cancelCreate"
        />
        <Button size="icon" variant="ghost" class="h-6 w-6 shrink-0 text-green-600" @click="saveCreate">
          <Check class="h-3.5 w-3.5" />
        </Button>
        <Button size="icon" variant="ghost" class="h-6 w-6 shrink-0 text-muted-foreground" @click="cancelCreate">
          <X class="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  </div>
</template>
