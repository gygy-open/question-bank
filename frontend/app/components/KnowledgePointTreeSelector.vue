<script setup lang="ts">
import { ref, computed } from 'vue'
import type { KnowledgePoint } from '~/types'
import { Folder, Search } from '@lucide/vue'
import { cn } from '@/lib/utils'
import ClearableInput from './ClearableInput.vue'
import KnowledgePointTreeItemSelector from './KnowledgePointTreeItemSelector.vue'

interface KnowledgePointNode extends KnowledgePoint {
  children: KnowledgePointNode[]
}

const props = defineProps<{
  knowledgePoints: KnowledgePoint[]
  selectedIds: string[]
}>()

const emit = defineEmits<{
  (e: 'toggle', id: string): void
  (e: 'clear'): void
}>()

const searchQuery = ref('')

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

// Keep a node's ancestor chain visible even when only a descendant matches the query.
function filterNode(node: KnowledgePointNode, query: string): KnowledgePointNode | null {
  const selfMatches = node.name.toLowerCase().includes(query)
  const filteredChildren = node.children
    .map(child => filterNode(child, query))
    .filter((n): n is KnowledgePointNode => n !== null)

  if (!selfMatches && filteredChildren.length === 0) return null
  return { ...node, children: filteredChildren }
}

const filteredTree = computed(() => {
  const query = searchQuery.value.trim().toLowerCase()
  if (!query) return tree.value
  return tree.value
    .map(node => filterNode(node, query))
    .filter((n): n is KnowledgePointNode => n !== null)
})
</script>

<template>
  <div class="space-y-2">
    <div class="relative">
      <Search class="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
      <ClearableInput v-model="searchQuery" placeholder="搜索知识点..." class="pl-7" autofocus />
    </div>

    <div class="space-y-0.5">
      <div 
        :class="cn(
          'flex items-center py-1 px-2 rounded-md cursor-pointer hover:bg-accent/50 text-sm transition-colors',
          selectedIds.length === 0 ? 'bg-accent text-accent-foreground font-medium' : 'text-muted-foreground'
        )"
        @click="emit('clear')"
      >
        <Folder class="w-4 h-4 mr-2 text-primary" />
        <span>全部知识点</span>
      </div>
      
      <KnowledgePointTreeItemSelector 
        v-for="node in filteredTree" 
        :key="node.id" 
        :node="node" 
        :level="0"
        :selected-ids="selectedIds"
        :search="searchQuery"
        @toggle="(id) => emit('toggle', id)"
      />

      <div v-if="searchQuery && filteredTree.length === 0" class="py-4 text-center text-xs text-muted-foreground">
        未找到匹配的知识点
      </div>
    </div>
  </div>
</template>
