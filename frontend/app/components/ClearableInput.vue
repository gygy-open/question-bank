<script setup lang="ts">
import { Input } from '@/components/ui/input'
import { X } from 'lucide-vue-next'
import { computed } from 'vue'

const props = defineProps<{
  modelValue?: string | number
  placeholder?: string
  type?: string
}>()

const emit = defineEmits(['update:modelValue'])

const showClear = computed(() => {
  return props.modelValue !== undefined && props.modelValue !== '' && props.modelValue !== null
})

const clear = () => {
  emit('update:modelValue', '')
}
</script>

<template>
  <div class="relative">
    <Input 
      :model-value="modelValue" 
      :type="type" 
      :placeholder="placeholder"
      @update:model-value="emit('update:modelValue', $event)"
      class="pr-8"
    />
    <button 
      v-if="showClear"
      @click="clear"
      class="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground p-1 rounded-full hover:bg-muted"
      type="button"
    >
      <X class="h-3 w-3" />
    </button>
  </div>
</template>
