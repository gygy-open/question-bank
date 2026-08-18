<script setup lang="ts">
import { computed } from 'vue'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Button } from '@/components/ui/button'
import { Settings2, Sparkles } from '@lucide/vue'
import { FIELD_ORDER, FIELD_LABEL, EXAMPLE_OVERRIDE } from '@/lib/displayPolicy'
import type { EditorBlock } from '../blockRegistry'
import type { DisplayField, DisplayRegion } from '~/types'

const props = defineProps<{ block: EditorBlock }>()
const emit = defineEmits<{ change: [] }>()

type Choice = 'inherit' | DisplayRegion
const CHOICES: { value: Choice; label: string }[] = [
  { value: 'inherit', label: '跟随文档' },
  { value: 'inline', label: '题后' },
  { value: 'appendix', label: '卷末' },
  { value: 'hidden', label: '不显示' },
]

const overrideOf = (field: DisplayField): Choice =>
  (props.block.content?.display?.fields?.[field]?.region as Choice) ?? 'inherit'

const setOverride = (field: DisplayField, value: Choice) => {
  const content = props.block.content
  if (!content.display) content.display = { fields: {} }
  if (!content.display.fields) content.display.fields = {}
  const fields = content.display.fields
  if (value === 'inherit') {
    delete fields[field]
    if (Object.keys(fields).length === 0) delete content.display
  } else {
    fields[field] = { region: value }
  }
  emit('change')
}

const markAsExample = () => {
  props.block.content.display = JSON.parse(JSON.stringify(EXAMPLE_OVERRIDE))
  emit('change')
}

const hasOverride = computed(() => {
  const fields = props.block.content?.display?.fields
  return !!fields && Object.keys(fields).length > 0
})
</script>

<template>
  <Popover>
    <PopoverTrigger as-child>
      <Button
        variant="ghost"
        size="icon"
        class="relative h-7 w-7 text-muted-foreground"
        title="本题显示设置"
      >
        <Settings2 class="h-4 w-4" />
        <span
          v-if="hasOverride"
          class="absolute right-0.5 top-0.5 h-1.5 w-1.5 rounded-full bg-primary"
        />
      </Button>
    </PopoverTrigger>
    <PopoverContent class="w-72 p-3" align="end" @click.stop>
      <div class="mb-2 flex items-center justify-between">
        <span class="text-sm font-medium">本题显示设置</span>
        <Button variant="secondary" size="sm" class="h-6 px-2 text-xs" @click="markAsExample">
          <Sparkles class="mr-1 h-3 w-3" /> 标为例题
        </Button>
      </div>
      <div class="space-y-2">
        <div v-for="f in FIELD_ORDER" :key="f" class="flex items-center gap-2">
          <span class="w-8 shrink-0 text-xs text-muted-foreground">{{ FIELD_LABEL[f] }}</span>
          <div class="flex flex-1 gap-0.5 rounded-md border p-0.5">
            <button
              v-for="c in CHOICES"
              :key="c.value"
              class="flex-1 rounded px-1 py-0.5 text-xs transition-colors"
              :class="overrideOf(f) === c.value ? 'bg-primary text-primary-foreground' : 'hover:bg-muted'"
              @click="setOverride(f, c.value)"
            >
              {{ c.label }}
            </button>
          </div>
        </div>
      </div>
    </PopoverContent>
  </Popover>
</template>
