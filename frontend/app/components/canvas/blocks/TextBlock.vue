<script setup lang="ts">
import { computed } from 'vue'
import TiptapEditor from '@/components/TiptapEditor.vue'
import type { EditorBlock } from '../blockRegistry'

const props = defineProps<{
  block: EditorBlock
}>()

const emit = defineEmits<{ change: [] }>()

const text = computed({
  get: () => props.block.content.text ?? '',
  set: (v: string | null) => {
    props.block.content.text = v ?? ''
    emit('change')
  },
})
</script>

<template>
  <div class="pl-8 pr-4">
    <TiptapEditor
      v-model="text"
      placeholder="输入文本内容，例如考试说明、注意事项、阅读材料…"
      min-height="60px"
    />
  </div>
</template>
