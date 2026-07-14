<script setup lang="ts">
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { X } from 'lucide-vue-next'
import { computed } from 'vue'

interface Option {
  label: string
  value: string
}

const props = defineProps<{
  modelValue?: string
  options: Option[]
  placeholder?: string
}>()

const emit = defineEmits(['update:modelValue'])

const showClear = computed(() => {
  return props.modelValue !== undefined && props.modelValue !== '' && props.modelValue !== '0'
})

const clear = (e: Event) => {
  e.stopPropagation()
  emit('update:modelValue', undefined)
}
</script>

<template>
  <div class="relative group">
    <Select :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)">
      <SelectTrigger class="w-full pr-8">
        <SelectValue :placeholder="placeholder" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem v-for="option in options" :key="option.value" :value="option.value">
          {{ option.label }}
        </SelectItem>
      </SelectContent>
    </Select>
    <button 
      v-if="showClear"
      @click="clear"
      class="absolute right-8 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground p-1 rounded-full hover:bg-muted z-10 opacity-0 group-hover:opacity-100 transition-opacity"
      type="button"
      title="清除"
    >
      <X class="h-3 w-3" />
    </button>
  </div>
</template>
