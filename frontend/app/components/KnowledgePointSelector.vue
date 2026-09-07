<script setup lang="ts">
import { ref, computed } from 'vue'
import { ChevronsUpDown, Search, X } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Badge } from '@/components/ui/badge'
import ClearableInput from './ClearableInput.vue'
import KnowledgePointTreeItem from './KnowledgePointTreeItem.vue'
import { buildKnowledgePointTree, filterKnowledgePointTree } from '@/lib/knowledgePointTree'
import type { KnowledgePoint } from '@/types'

const props = withDefaults(defineProps<{
  modelValue: number[]
  knowledgePoints: KnowledgePoint[]
  disabled?: boolean
}>(), {
  disabled: false
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: number[]): void
}>()

const open = ref(false)
const searchQuery = ref('')

const tree = computed(() => buildKnowledgePointTree(props.knowledgePoints ?? []))
const filteredTree = computed(() => filterKnowledgePointTree(tree.value, searchQuery.value))
// KnowledgePointTreeItem works with string ids so it can be shared with the filter-side tree selector.
const selectedIdStrings = computed(() => props.modelValue.map(String))

const selectedEntries = computed(() => {
  return props.modelValue.map(id => ({
    id,
    label: props.knowledgePoints.find(c => c.id === id)?.name ?? String(id),
  }))
})

const handleToggle = (idStr: string) => {
  const id = Number(idStr)
  const newIds = [...props.modelValue]
  const index = newIds.indexOf(id)
  if (index > -1) {
    newIds.splice(index, 1)
  } else {
    newIds.push(id)
  }
  emit('update:modelValue', newIds)
}

const remove = (id: number) => {
  emit('update:modelValue', props.modelValue.filter(v => v !== id))
}
</script>

<template>
  <Popover v-model:open="open">
    <PopoverTrigger as-child>
      <Button
        variant="outline"
        role="combobox"
        :aria-expanded="open"
        class="w-full justify-between h-auto min-h-10"
        :disabled="disabled"
      >
        <div class="flex flex-wrap gap-1 text-left">
          <span v-if="modelValue.length === 0" class="text-muted-foreground">选择知识点...</span>
          <Badge 
            v-for="entry in selectedEntries" 
            :key="entry.id" 
            variant="secondary"
            class="mr-1"
          >
            {{ entry.label }}
            <button 
              type="button"
              class="ml-1 inline-flex h-3 w-3 items-center justify-center text-muted-foreground hover:text-foreground"
              @mousedown.stop.prevent
              @click.stop.prevent="remove(entry.id)"
            >
              <X class="h-3 w-3" aria-hidden="true" />
              <span class="sr-only">移除 {{ entry.label }}</span>
            </button>
          </Badge>
        </div>
        <ChevronsUpDown class="ml-2 h-4 w-4 shrink-0 opacity-50" />
      </Button>
    </PopoverTrigger>
    <PopoverContent class="w-(--reka-popover-trigger-width) min-w-[280px] p-2">
      <div class="relative mb-2">
        <Search class="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
        <ClearableInput v-model="searchQuery" placeholder="搜索知识点..." class="pl-7" autofocus />
      </div>
      <div class="max-h-[300px] overflow-y-auto">
        <KnowledgePointTreeItem 
          v-for="node in filteredTree"
          :key="node.id"
          :node="node" 
          :level="0"
          :selected-ids="selectedIdStrings"
          :search="searchQuery"
          @toggle="handleToggle" 
        />
        <div v-if="searchQuery && filteredTree.length === 0" class="py-4 text-center text-xs text-muted-foreground">
          未找到匹配的知识点
        </div>
      </div>
    </PopoverContent>
  </Popover>
</template>

