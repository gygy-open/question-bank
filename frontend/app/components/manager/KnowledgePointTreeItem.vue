<script setup lang="ts">
import { ref, computed, nextTick, watch } from 'vue'
import { ChevronRight, ChevronDown, Plus, Pencil, Trash2, Folder, FolderOpen, Save, X, GripVertical } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import type { KnowledgePoint } from '@/types'

// Extend KnowledgePoint to include children for the tree view
interface KnowledgePointNode extends KnowledgePoint {
  children?: KnowledgePointNode[]
}

const props = defineProps<{
  knowledgePoint: KnowledgePointNode
  level?: number
}>()

const emit = defineEmits<{
  (e: 'update', id: number, data: { name: string, slug: string }): void
  (e: 'delete', id: number): void
  (e: 'create', parentId: number, data: { name: string, slug: string }): void
  (e: 'move', draggedId: number, targetId: number): void
}>()

const isOpen = ref(false)
const hasChildren = computed(() => props.knowledgePoint.children && props.knowledgePoint.children.length > 0)

// --- Inline Edit State ---
const isEditing = ref(false)
const editName = ref('')
const editSlug = ref('')

// --- Inline Create State ---
const isCreating = ref(false)
const newName = ref('')
const newSlug = ref('')

// --- Drag & Drop State ---
const isDragOver = ref(false)

const toggleOpen = () => {
  if (hasChildren.value) {
    isOpen.value = !isOpen.value
  }
}

// --- Edit Handlers ---
const editInputRef = ref<any>(null)
const createInputRef = ref<any>(null)

const startEdit = async () => {
  editName.value = props.knowledgePoint.name
  editSlug.value = props.knowledgePoint.slug
  isEditing.value = true
  await nextTick()
  editInputRef.value?.$el?.focus()
}

const cancelEdit = () => {
  isEditing.value = false
}

const saveEdit = () => {
  if (!editName.value.trim() || !editSlug.value.trim()) return
  emit('update', props.knowledgePoint.id, { name: editName.value, slug: editSlug.value })
  isEditing.value = false
}

// --- Create Handlers ---
const startCreate = async () => {
  newName.value = ''
  newSlug.value = ''
  isCreating.value = true
  isOpen.value = true // Ensure children are visible
  await nextTick()
  createInputRef.value?.$el?.focus()
}

const cancelCreate = () => {
  isCreating.value = false
}

const saveCreate = () => {
  if (!newName.value.trim() || !newSlug.value.trim()) return
  emit('create', props.knowledgePoint.id, { name: newName.value, slug: newSlug.value })
  isCreating.value = false
  isOpen.value = true
}

// --- Drag & Drop Handlers ---
const onDragStart = (event: DragEvent) => {
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', String(props.knowledgePoint.id))
    // Add a class to body or something to indicate dragging?
  }
}

const onDragOver = (event: DragEvent) => {
  // Prevent dropping on itself or its children (handled by logic, but visual feedback here)
  // We can't easily check children recursion here without more state, 
  // but we can at least allow the drop event.
  event.preventDefault()
  event.dataTransfer!.dropEffect = 'move'
  isDragOver.value = true
}

const onDragLeave = () => {
  isDragOver.value = false
}

const onDrop = (event: DragEvent) => {
  event.preventDefault()
  isDragOver.value = false
  const draggedId = Number(event.dataTransfer?.getData('text/plain'))
  if (draggedId && draggedId !== props.knowledgePoint.id) {
    emit('move', draggedId, props.knowledgePoint.id)
  }
}

// Auto-generate slug from name for convenience
watch(newName, (val) => {
  if (!isCreating.value) return
  // Simple slugify: lowercase, replace spaces with dashes
  newSlug.value = val.toLowerCase().replace(/\s+/g, '-')
})
</script>

<template>
  <div class="select-none">
    <!-- Node Row -->
    <div 
      class="flex items-center py-2 px-2 rounded-md group transition-colors border border-transparent"
      :class="{ 
        'bg-muted/50': !isDragOver, 
        'bg-primary/10 border-primary/50': isDragOver 
      }"
      :style="{ paddingLeft: `${(level || 0) * 24 + 8}px` }"
      draggable="true"
      @dragstart.stop="onDragStart"
      @dragover.stop="onDragOver"
      @dragleave.stop="onDragLeave"
      @drop.stop="onDrop"
    >
      <!-- Drag Handle (Visual only, whole row is draggable) -->
      <GripVertical class="w-4 h-4 text-muted-foreground/50 mr-1 cursor-grab active:cursor-grabbing" />

      <!-- Expand/Collapse Icon -->
      <button 
        @click.stop="toggleOpen"
        class="mr-1 p-0.5 rounded-sm hover:bg-muted text-muted-foreground"
        :class="{ 'invisible': !hasChildren && !isCreating }"
      >
        <ChevronDown v-if="isOpen" class="w-4 h-4" />
        <ChevronRight v-else class="w-4 h-4" />
      </button>

      <!-- Folder Icon -->
      <div class="mr-2 text-blue-500/80">
        <FolderOpen v-if="isOpen" class="w-4 h-4" />
        <Folder v-else class="w-4 h-4" />
      </div>

      <!-- Content: Display or Edit Mode -->
      <div v-if="isEditing" class="flex-1 flex items-center gap-2 mr-2">
        <Input ref="editInputRef" v-model="editName" class="h-7 text-sm" placeholder="名称" @keyup.enter="saveEdit" @keyup.esc="cancelEdit" />
        <Input v-model="editSlug" class="h-7 text-sm w-24" placeholder="Slug" @keyup.enter="saveEdit" @keyup.esc="cancelEdit" />
        <Button size="icon" variant="ghost" class="h-7 w-7 text-green-600" @click.stop="saveEdit">
          <Save class="w-4 h-4" />
        </Button>
        <Button size="icon" variant="ghost" class="h-7 w-7 text-muted-foreground" @click.stop="cancelEdit">
          <X class="w-4 h-4" />
        </Button>
      </div>

      <span v-else class="text-sm font-medium flex-1 truncate cursor-default flex items-center" @click="toggleOpen">
        {{ knowledgePoint.name }}
        <span class="ml-2 text-xs text-muted-foreground font-normal">
          /{{ knowledgePoint.slug }}
        </span>
      </span>

      <!-- Actions (Visible on Hover) -->
      <div v-if="!isEditing" class="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <Button 
          variant="ghost" 
          size="icon" 
          class="h-7 w-7" 
          @click.stop="startCreate"
          title="添加子目录"
        >
          <Plus class="w-3.5 h-3.5" />
        </Button>
        <Button 
          variant="ghost" 
          size="icon" 
          class="h-7 w-7" 
          @click.stop="startEdit"
          title="编辑"
        >
          <Pencil class="w-3.5 h-3.5" />
        </Button>
        <Button 
          variant="ghost" 
          size="icon" 
          class="h-7 w-7 text-destructive hover:text-destructive" 
          @click.stop="$emit('delete', knowledgePoint.id)"
          title="删除"
        >
          <Trash2 class="w-3.5 h-3.5" />
        </Button>
      </div>
    </div>

    <!-- Children Container -->
    <div v-if="isOpen">
      <!-- Existing Children -->
      <KnowledgePointTreeItem
        v-for="child in knowledgePoint.children"
        :key="child.id"
        :knowledge-point="child"
        :level="(level || 0) + 1"
        @update="(id, data) => $emit('update', id, data)"
        @delete="(id) => $emit('delete', id)"
        @create="(pid, data) => $emit('create', pid, data)"
        @move="(did, tid) => $emit('move', did, tid)"
      />

      <!-- Inline Create Form -->
      <div 
        v-if="isCreating" 
        class="flex items-center py-2 px-2 rounded-md bg-muted/30"
        :style="{ paddingLeft: `${((level || 0) + 1) * 24 + 8}px` }"
      >
        <div class="w-4 h-4 mr-1"></div> <!-- Indent for expand icon -->
        <div class="mr-2 text-muted-foreground">
          <Folder class="w-4 h-4" />
        </div>
        <div class="flex-1 flex items-center gap-2">
          <Input ref="createInputRef" v-model="newName" class="h-7 text-sm" placeholder="新目录名称" @keyup.enter="saveCreate" @keyup.esc="cancelCreate" />
          <Input v-model="newSlug" class="h-7 text-sm w-24" placeholder="Slug" @keyup.enter="saveCreate" @keyup.esc="cancelCreate" />
          <Button size="icon" variant="ghost" class="h-7 w-7 text-green-600" @click="saveCreate">
            <Save class="w-4 h-4" />
          </Button>
          <Button size="icon" variant="ghost" class="h-7 w-7 text-muted-foreground" @click="cancelCreate">
            <X class="w-4 h-4" />
          </Button>
        </div>
      </div>
    </div>
  </div>
</template>
