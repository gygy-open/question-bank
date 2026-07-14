<script setup lang="ts">
import { ref, computed } from 'vue'
import { ChevronRight, ChevronDown, Check } from 'lucide-vue-next'
import { cn } from '@/lib/utils'
import type { KnowledgePoint } from '@/types'

interface KnowledgePointNode extends KnowledgePoint {
  children: KnowledgePointNode[]
}

const props = defineProps<{
  node: KnowledgePointNode
  level: number
  selectedIds: number[]
}>()

const emit = defineEmits<{
  (e: 'toggle', id: number): void
}>()

const isOpen = ref(false)
const hasChildren = computed(() => props.node.children && props.node.children.length > 0)

const toggleOpen = (e: Event) => {
  e.stopPropagation()
  if (hasChildren.value) isOpen.value = !isOpen.value
}

const isSelected = computed(() => props.selectedIds.includes(props.node.id))

const toggleSelection = () => {
  emit('toggle', props.node.id)
}
</script>

<template>
  <div>
    <div 
      :class="cn(
        'flex items-center py-1 px-2 rounded-md cursor-pointer hover:bg-accent/50 text-sm transition-colors select-none',
        isSelected ? 'bg-accent/20' : ''
      )"
      :style="{ paddingLeft: `${level * 12 + 8}px` }"
      @click="toggleSelection"
    >
      <div 
        class="mr-1 p-0.5 rounded-sm hover:bg-muted/80 text-muted-foreground/70"
        @click.stop="toggleOpen"
      >
        <ChevronDown v-if="hasChildren && isOpen" class="w-3 h-3" />
        <ChevronRight v-else-if="hasChildren" class="w-3 h-3" />
        <div v-else class="w-3 h-3" />
      </div>
      
      <div 
        class="mr-2 flex items-center justify-center w-4 h-4 border rounded-sm transition-colors" 
        :class="isSelected ? 'bg-primary border-primary text-primary-foreground' : 'border-muted-foreground'"
      >
         <Check v-if="isSelected" class="w-3 h-3" />
      </div>
      
      <span class="truncate">{{ node.name }}</span>
    </div>
    
    <div v-if="isOpen && hasChildren">
      <KnowledgePointTreeCheckbox
        v-for="child in node.children"
        :key="child.id"
        :node="child"
        :level="level + 1"
        :selected-ids="selectedIds"
        @toggle="(id) => emit('toggle', id)"
      />
    </div>
  </div>
</template>
