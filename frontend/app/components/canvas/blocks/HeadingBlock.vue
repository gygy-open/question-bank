<script setup lang="ts">
import { computed } from 'vue'
import { Input } from '@/components/ui/input'
import type { EditorBlock } from '../blockRegistry'

const props = defineProps<{
  block: EditorBlock
}>()

const emit = defineEmits<{ change: [] }>()

const text = computed({
  get: () => props.block.content.text ?? '',
  set: (v: string) => {
    props.block.content.text = v
    emit('change')
  },
})
</script>

<template>
  <div class="pl-8 pr-4">
    <Input
      v-model="text"
      placeholder="大题标题，例如：一、选择题"
      class="h-9 text-lg font-bold border-transparent hover:border-input focus-visible:border-input px-2"
    />
  </div>
</template>
