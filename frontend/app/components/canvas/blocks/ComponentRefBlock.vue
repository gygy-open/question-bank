<script setup lang="ts">
import { computed } from 'vue'
import { Blocks } from '@lucide/vue'
import type { EditorBlock } from '../blockRegistry'

const props = defineProps<{
  block: EditorBlock
}>()

const compTypeLabels: Record<string, string> = {
  question_group: '教学模块', exam_paper: '试卷', study_guide: '学案', handout: '讲义',
}

const refComp = computed(() => props.block.ref_composition)
const label = computed(() => (refComp.value ? compTypeLabels[refComp.value.comp_type] || refComp.value.comp_type : null))
</script>

<template>
  <div class="pl-8 pr-16 py-2">
    <div class="flex items-center gap-2 rounded-md border-l-4 border-primary bg-primary/5 px-3 py-2">
      <Blocks class="h-4 w-4 shrink-0 text-primary" />
      <template v-if="refComp">
        <span class="font-medium truncate">{{ refComp.title }}</span>
        <span class="shrink-0 rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary">{{ label }}</span>
        <span class="ml-auto shrink-0 text-xs text-muted-foreground">保持同步</span>
      </template>
      <span v-else class="text-muted-foreground italic">引用的内容已删除</span>
    </div>
  </div>
</template>
