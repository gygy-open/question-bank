<script setup lang="ts">
import { ref, computed } from 'vue'
import { ChevronsUpDown, X } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Badge } from '@/components/ui/badge'
import KnowledgePointTreeCheckbox from './KnowledgePointTreeCheckbox.vue'
import type { KnowledgePoint } from '@/types'

interface KnowledgePointNode extends KnowledgePoint {
  children: KnowledgePointNode[]
}

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

// Build tree
const tree = computed<KnowledgePointNode[]>(() => {
  if (!props.knowledgePoints) return []
  const map = new Map<number, KnowledgePointNode>()
  const roots: KnowledgePointNode[] = []
  
  // Clone
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

const selectedLabels = computed(() => {
  return props.modelValue.map(id => {
    const kp = props.knowledgePoints.find(c => c.id === id)
    return kp ? kp.name : id
  })
})

const handleUpdate = (id: number) => {
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
            v-for="(label, index) in selectedLabels" 
            :key="modelValue[index]" 
            variant="secondary"
            class="mr-1"
          >
            {{ label }}
            <button 
              type="button"
              class="ml-1 inline-flex h-3 w-3 items-center justify-center text-muted-foreground hover:text-foreground"
              @mousedown.stop.prevent
              @click.stop.prevent="remove(modelValue[index])"
            >
              <X class="h-3 w-3" aria-hidden="true" />
              <span class="sr-only">移除 {{ label }}</span>
            </button>
          </Badge>
        </div>
        <ChevronsUpDown class="ml-2 h-4 w-4 shrink-0 opacity-50" />
      </Button>
    </PopoverTrigger>
    <PopoverContent class="w-[400px] p-0">
      <div class="p-2 max-h-[300px] overflow-y-auto">
        <KnowledgePointTreeCheckbox 
          v-for="node in tree"
          :key="node.id"
          :node="node" 
          :level="0"
          :selected-ids="modelValue" 
          @toggle="handleUpdate" 
        />
      </div>
    </PopoverContent>
  </Popover>
</template>
