<script setup lang="ts">
import { ref } from 'vue'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Button } from '@/components/ui/button'
import { Plus } from '@lucide/vue'
import { insertableBlocks } from './blockRegistry'
import type { BlockType } from '~/types'

const emit = defineEmits<{ insert: [type: BlockType] }>()
const open = ref(false)

const pick = (type: BlockType) => {
  open.value = false
  emit('insert', type)
}
</script>

<template>
  <Popover :open="open" @update:open="open = $event">
    <PopoverTrigger as-child>
      <Button variant="secondary" size="sm" class="h-6 px-2 text-xs shadow-sm">
        <Plus class="mr-1 h-3 w-3" /> 插入内容
      </Button>
    </PopoverTrigger>
    <PopoverContent class="w-44 p-1" align="center">
      <button
        v-for="b in insertableBlocks"
        :key="b.type"
        class="w-full flex items-center gap-2 px-2 py-1.5 text-sm rounded-md hover:bg-muted transition-colors text-left"
        @click="pick(b.type)"
      >
        <component :is="b.icon" class="h-4 w-4 text-muted-foreground" />
        {{ b.label }}
      </button>
    </PopoverContent>
  </Popover>
</template>
