<script setup lang="ts">
import { computed } from 'vue'
import {
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
} from '@/components/ui/dropdown-menu'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { Settings2, X } from '@lucide/vue'
import { FIELD_ORDER, FIELD_LABEL } from '@/lib/displayPolicy'
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

const setOverride = (field: DisplayField, value: Choice | undefined) => {
  if (!value) return
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

// 输入框内容 (哪怕删空成 "") 与"完全没有覆盖"是两个不同状态, 后者要靠下面的清除按钮
const labelOverride = computed({
  get: () => props.block.content.label_override ?? '',
  set: (v: string) => {
    props.block.content.label_override = v
    emit('change')
  },
})
const hasLabelOverride = computed(() => props.block.content.label_override !== undefined)
const clearLabelOverride = () => {
  delete props.block.content.label_override
  emit('change')
}

const hasOverride = computed(() => {
  const fields = props.block.content?.display?.fields
  return (!!fields && Object.keys(fields).length > 0) || hasLabelOverride.value
})
</script>

<template>
  <DropdownMenuSub>
    <DropdownMenuSubTrigger>
      <Settings2 /> 显示设置
      <span
        v-if="hasOverride"
        class="ml-1 h-1.5 w-1.5 shrink-0 rounded-full bg-primary"
      />
    </DropdownMenuSubTrigger>
    <DropdownMenuSubContent class="w-72 p-3" @click.stop>
      <div class="mb-2 text-sm font-medium">本题显示设置</div>

      <div class="mb-3 flex items-center gap-2">
        <span class="w-9 shrink-0 text-xs text-muted-foreground">题号</span>
        <Input
          v-model="labelOverride"
          placeholder="留空则自动编号"
          class="h-7 flex-1 text-xs"
          @keydown.stop
        />
        <Button
          v-if="hasLabelOverride"
          variant="ghost"
          size="icon"
          class="h-7 w-7 shrink-0"
          title="恢复自动编号"
          @click="clearLabelOverride"
        >
          <X class="h-3.5 w-3.5" />
        </Button>
      </div>

      <div class="space-y-2">
        <div v-for="f in FIELD_ORDER" :key="f" class="flex items-center gap-2">
          <span class="w-9 shrink-0 text-xs text-muted-foreground">{{ FIELD_LABEL[f] }}</span>
          <ToggleGroup
            type="single"
            :model-value="overrideOf(f)"
            class="flex-1"
            :spacing="0"
            variant="outline"
            size="sm"
            @update:model-value="(v) => setOverride(f, v as Choice | undefined)"
          >
            <ToggleGroupItem v-for="c in CHOICES" :key="c.value" :value="c.value" class="flex-1 text-xs">
              {{ c.label }}
            </ToggleGroupItem>
          </ToggleGroup>
        </div>
      </div>
    </DropdownMenuSubContent>
  </DropdownMenuSub>
</template>
