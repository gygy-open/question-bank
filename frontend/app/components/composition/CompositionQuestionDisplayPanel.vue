<script setup lang="ts">
import { Switch } from '@/components/ui/switch'
import { Eye } from '@lucide/vue'
import { ANSWER_FIELD_KEYS } from '@/types/composition'
import type { AnswerFieldKey } from '@/types/composition'

defineProps<{
  fields: Record<AnswerFieldKey, boolean>
  disabled?: boolean
}>()

const emit = defineEmits<{
  toggle: [key: AnswerFieldKey, value: boolean]
}>()

const FIELD_LABELS: Record<AnswerFieldKey, string> = {
  answer: '答案',
  thinking: '思路',
  analysis: '解析',
  summary: '小结',
}
</script>

<template>
  <div class="rounded-lg border bg-card p-4">
    <div class="flex items-center gap-2">
      <Eye class="h-4 w-4 text-muted-foreground" />
      <span class="text-sm font-medium">题目显示</span>
    </div>
    <p class="mt-1.5 text-xs text-muted-foreground">
      题干与选项始终显示；下列字段可全局开关，也可在每道题上单独覆盖。
    </p>
    <div class="mt-3 space-y-2">
      <label
        v-for="key in ANSWER_FIELD_KEYS"
        :key="key"
        class="flex items-center justify-between text-sm"
      >
        {{ FIELD_LABELS[key] }}
        <Switch
          :model-value="fields[key]"
          :disabled="disabled"
          @update:model-value="emit('toggle', key, $event)"
        />
      </label>
    </div>
  </div>
</template>
