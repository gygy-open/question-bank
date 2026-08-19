<script setup lang="ts">
import { computed } from 'vue'
import { Input } from '@/components/ui/input'
import type { EditorBlock } from '../blockRegistry'

const props = defineProps<{
  block: EditorBlock
}>()

const emit = defineEmits<{ change: [] }>()

const level = computed<number>(() => props.block.content.level ?? 2)

const text = computed({
  get: () => props.block.content.text ?? '',
  set: (v: string) => {
    props.block.content.text = v
    emit('change')
  },
})

/** Notion 式无边框文本: 平时看起来就是纯文字, 只有 hover/聚焦时给一点背景提示可编辑。 */
const inputClass = computed(() => {
  const base = 'w-full rounded-sm border-0 bg-transparent px-1 shadow-none outline-none ring-0 '
    + 'hover:bg-muted/50 focus-visible:bg-muted/50 focus-visible:ring-0 focus-visible:border-0'
  switch (level.value) {
    case 1: return `${base} h-12 text-center text-2xl font-bold`
    case 3: return `${base} h-8 text-base font-semibold`
    case 4: return `${base} h-7 text-sm font-medium`
    default: return `${base} h-9 text-lg font-bold`
  }
})
</script>

<template>
  <div :class="level === 1 ? 'px-4' : 'pl-8 pr-4'">
    <Input
      v-model="text"
      placeholder="标题，例如：一、选择题"
      :class="inputClass"
    />
  </div>
</template>
