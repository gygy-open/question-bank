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

const { t } = useI18n()

const FIELD_LABEL_KEYS: Record<AnswerFieldKey, string> = {
  answer: 'compositionPanels.fields.answer',
  thinking: 'compositionPanels.fields.thinking',
  analysis: 'compositionPanels.fields.analysis',
  summary: 'compositionPanels.fields.summary',
}
</script>

<template>
  <div>
    <div class="flex items-center gap-2">
      <Eye class="h-4 w-4 text-muted-foreground" />
      <span class="text-sm font-medium">{{ t('compositionPanels.display.title') }}</span>
    </div>
    <p class="mt-1.5 text-xs text-muted-foreground">
      {{ t('compositionPanels.display.hint') }}
    </p>
    <div class="mt-3 space-y-2">
      <label
        v-for="key in ANSWER_FIELD_KEYS"
        :key="key"
        class="flex items-center justify-between text-sm"
      >
        {{ t(FIELD_LABEL_KEYS[key]) }}
        <Switch
          :model-value="fields[key]"
          :disabled="disabled"
          @update:model-value="emit('toggle', key, $event)"
        />
      </label>
    </div>
  </div>
</template>
