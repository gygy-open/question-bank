<script setup lang="ts">
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Button } from '@/components/ui/button'
import { Settings } from '@lucide/vue'
import { FIELD_ORDER, FIELD_LABEL } from '@/lib/displayPolicy'
import type { DisplayPolicy, DisplayField, DisplayRegion } from '~/types'

const props = defineProps<{ modelValue: DisplayPolicy | null | undefined }>()
const emit = defineEmits<{ 'update:modelValue': [DisplayPolicy] }>()

const REGIONS: { value: DisplayRegion; label: string }[] = [
  { value: 'inline', label: '题后' },
  { value: 'appendix', label: '卷末' },
  { value: 'hidden', label: '不显示' },
]

const regionOf = (field: DisplayField): DisplayRegion =>
  props.modelValue?.fields?.[field]?.region ?? 'hidden'

const setRegion = (field: DisplayField, region: DisplayRegion) => {
  const base = props.modelValue?.fields ?? {}
  emit('update:modelValue', {
    v: props.modelValue?.v ?? 1,
    fields: { ...base, [field]: { region } },
  })
}
</script>

<template>
  <Popover>
    <PopoverTrigger as-child>
      <Button variant="outline" size="sm">
        <Settings class="mr-2 h-4 w-4" /> 文档设置
      </Button>
    </PopoverTrigger>
    <PopoverContent class="w-80 p-3" align="end">
      <div class="mb-2 text-sm font-medium">内容显示（题目附属内容落位）</div>
      <div class="space-y-2">
        <div v-for="f in FIELD_ORDER" :key="f" class="flex items-center gap-2">
          <span class="w-8 shrink-0 text-xs text-muted-foreground">{{ FIELD_LABEL[f] }}</span>
          <div class="flex flex-1 gap-0.5 rounded-md border p-0.5">
            <button
              v-for="r in REGIONS"
              :key="r.value"
              class="flex-1 rounded px-1 py-1 text-xs transition-colors"
              :class="regionOf(f) === r.value ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'"
              @click="setRegion(f, r.value)"
            >
              {{ r.label }}
            </button>
          </div>
        </div>
      </div>
      <p class="mt-2 text-xs text-muted-foreground">题目可单独覆盖此设置。</p>
    </PopoverContent>
  </Popover>
</template>
