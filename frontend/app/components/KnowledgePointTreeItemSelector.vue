<script setup lang="ts">
import { ref, computed } from 'vue'
import { ChevronRight, ChevronDown, Folder, FolderOpen } from 'lucide-vue-next'
import { cn } from '@/lib/utils'
import type { KnowledgePoint } from '@/types'

interface KnowledgePointNode extends KnowledgePoint {
  children: KnowledgePointNode[]
}

const props = defineProps<{
  node: KnowledgePointNode
  level: number
  selectedId?: string
}>()

const emit = defineEmits<{
  (e: 'select', id: string): void
}>()

const isOpen = ref(false)
const hasChildren = computed(() => props.node.children && props.node.children.length > 0)

const toggle = (e: Event) => {
  e.stopPropagation()
  if (hasChildren.value) isOpen.value = !isOpen.value
}

const select = () => {
  emit('select', String(props.node.id))
}
</script>

<template>
  <div>
    <div 
      :class="cn(
        'flex items-center py-1 px-2 rounded-md cursor-pointer hover:bg-accent/50 text-sm transition-colors',
        selectedId === String(node.id) ? 'bg-accent text-accent-foreground font-medium' : 'text-muted-foreground'
      )"
      :style="{ paddingLeft: `${level * 12 + 8}px` }"
      @click="select"
    >
      <div 
        class="mr-1 p-0.5 rounded-sm hover:bg-muted/80 text-muted-foreground/70"
        @click.stop="toggle"
      >
        <ChevronDown v-if="hasChildren && isOpen" class="w-3 h-3" />
        <ChevronRight v-else-if="hasChildren" class="w-3 h-3" />
        <div v-else class="w-3 h-3" />
      </div>
      
      <FolderOpen v-if="isOpen" class="w-4 h-4 mr-2 text-blue-500" />
      <Folder v-else class="w-4 h-4 mr-2 text-blue-500" />
      
      <span class="truncate">{{ node.name }}</span>
    </div>
    
    <div v-if="isOpen && hasChildren">
      <KnowledgePointTreeItemSelector
        v-for="child in node.children"
        :key="child.id"
        :node="child"
        :level="level + 1"
        :selected-id="selectedId"
        @select="(id) => emit('select', id)"
      />
    </div>
  </div>
</template>
