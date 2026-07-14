<script setup lang="ts">
import { computed } from 'vue'
import type { KnowledgePoint } from '~/types'
import { Folder } from 'lucide-vue-next'
import { cn } from '@/lib/utils'
import KnowledgePointTreeItemSelector from './KnowledgePointTreeItemSelector.vue'

interface KnowledgePointNode extends KnowledgePoint {
  children: KnowledgePointNode[]
}

const props = defineProps<{
  knowledgePoints: KnowledgePoint[]
  selectedId?: string
}>()

const emit = defineEmits<{
  (e: 'select', id: string | undefined): void
}>()

const tree = computed<KnowledgePointNode[]>(() => {
  if (!props.knowledgePoints) return []
  const map = new Map<number, KnowledgePointNode>()
  const roots: KnowledgePointNode[] = []
  
  // Clone to avoid mutation issues if reused
  props.knowledgePoints.forEach(kp => {
    map.set(kp.id, { ...kp, children: [] })
  })
  
  props.knowledgePoints.forEach(kp => {
    const node = map.get(kp.id)!
    if (kp.parent_id) {
      const parent = map.get(kp.parent_id)
      if (parent) {
        parent.children.push(node)
      } else {
        roots.push(node)
      }
    } else {
      roots.push(node)
    }
  })
  return roots
})
</script>

<template>
  <div class="space-y-0.5">
    <div 
      :class="cn(
        'flex items-center py-1 px-2 rounded-md cursor-pointer hover:bg-accent/50 text-sm transition-colors',
        !selectedId ? 'bg-accent text-accent-foreground font-medium' : 'text-muted-foreground'
      )"
      @click="emit('select', undefined)"
    >
      <Folder class="w-4 h-4 mr-2 text-blue-500" />
      <span>全部知识点</span>
    </div>
    
    <KnowledgePointTreeItemSelector 
      v-for="node in tree" 
      :key="node.id" 
      :node="node" 
      :level="0"
      :selected-id="selectedId"
      @select="(id) => emit('select', id)"
    />
  </div>
</template>
