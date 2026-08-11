<script setup lang="ts">
import { ref, computed } from 'vue'
import { ChevronRight, ChevronDown, Folder, FolderOpen, Check } from '@lucide/vue'
import { cn } from '@/lib/utils'
import type { KnowledgePoint } from '@/types'

interface KnowledgePointNode extends KnowledgePoint {
  children: KnowledgePointNode[]
}

const props = defineProps<{
  node: KnowledgePointNode
  level: number
  selectedIds: string[]
  search?: string
}>()

const emit = defineEmits<{
  (e: 'toggle', id: string): void
}>()

const isOpen = ref(false)
const hasChildren = computed(() => props.node.children && props.node.children.length > 0)
const isSelected = computed(() => props.selectedIds.includes(String(props.node.id)))
// While searching, force-expand every branch so matches deep in the tree stay visible.
const isExpanded = computed(() => (props.search ? true : isOpen.value))

const toggleOpen = (e: Event) => {
  e.stopPropagation()
  isOpen.value = !isOpen.value
}

const toggleSelect = () => {
  emit('toggle', String(props.node.id))
}

// Rows with children expand/collapse on click; leaf rows have nothing to expand, so they select instead.
const onRowClick = (e: Event) => {
  if (hasChildren.value) {
    toggleOpen(e)
  } else {
    toggleSelect()
  }
}

const nameParts = computed(() => {
  const q = props.search?.trim()
  if (!q) return null
  const idx = props.node.name.toLowerCase().indexOf(q.toLowerCase())
  if (idx === -1) return null
  return {
    before: props.node.name.slice(0, idx),
    match: props.node.name.slice(idx, idx + q.length),
    after: props.node.name.slice(idx + q.length),
  }
})
</script>

<template>
  <div>
    <div 
      :class="cn(
        'flex items-center py-1 px-2 rounded-md cursor-pointer hover:bg-accent/50 text-sm transition-colors',
        isSelected ? 'bg-accent text-accent-foreground font-medium' : 'text-muted-foreground'
      )"
      :style="{ paddingLeft: `${level * 12 + 8}px` }"
      @click="onRowClick"
    >
      <div class="mr-1 p-0.5 rounded-sm text-muted-foreground/70">
        <ChevronDown v-if="hasChildren && isExpanded" class="w-3 h-3" />
        <ChevronRight v-else-if="hasChildren" class="w-3 h-3" />
        <div v-else class="w-3 h-3" />
      </div>

      <div
        :class="cn(
          'mr-2 flex h-4 w-4 shrink-0 items-center justify-center rounded-sm border border-primary',
          isSelected ? 'bg-primary text-primary-foreground' : 'opacity-50 [&_svg]:invisible'
        )"
        @click.stop="toggleSelect"
      >
        <Check class="h-3 w-3" />
      </div>

      <FolderOpen v-if="isExpanded" class="w-4 h-4 mr-2 text-primary shrink-0" />
      <Folder v-else class="w-4 h-4 mr-2 text-primary shrink-0" />
      
      <span v-if="nameParts" class="truncate">{{ nameParts.before }}<mark class="bg-primary/20 text-inherit rounded-sm">{{ nameParts.match }}</mark>{{ nameParts.after }}</span>
      <span v-else class="truncate">{{ node.name }}</span>
    </div>
    
    <div v-if="isExpanded && hasChildren">
      <KnowledgePointTreeItemSelector
        v-for="child in node.children"
        :key="child.id"
        :node="child"
        :level="level + 1"
        :selected-ids="selectedIds"
        :search="search"
        @toggle="(id) => emit('toggle', id)"
      />
    </div>
  </div>
</template>
