<script setup lang="ts">
import { ref } from 'vue'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { ListOrdered, Wand2 } from '@lucide/vue'
import type { NumberingMode } from '@/lib/compositionDocument'

defineProps<{
  enabled: boolean
  disabled?: boolean
}>()

const emit = defineEmits<{
  'update:enabled': [value: boolean]
  autofill: [mode: NumberingMode]
}>()

const { t } = useI18n()

const mode = ref<NumberingMode>('global')
</script>

<template>
  <div>
    <div class="flex items-center justify-between gap-2">
      <div class="flex items-center gap-2">
        <ListOrdered class="h-4 w-4 text-muted-foreground" />
        <span class="text-sm font-medium">{{ t('compositionPanels.numbering.title') }}</span>
      </div>
      <Switch
        :model-value="enabled"
        :disabled="disabled"
        @update:model-value="emit('update:enabled', $event)"
      />
    </div>
    <p class="mt-1.5 text-xs text-muted-foreground">
      {{ t('compositionPanels.numbering.hint') }}
    </p>

    <template v-if="enabled">
      <div class="mt-4 space-y-2">
        <Label class="text-xs text-muted-foreground">{{ t('compositionPanels.numbering.autofillMode') }}</Label>
        <RadioGroup v-model="mode" class="gap-2">
          <label class="flex items-start gap-2 text-sm">
            <RadioGroupItem value="global" class="mt-0.5" />
            <span>
              {{ t('compositionPanels.numbering.global') }}
              <span class="block text-xs text-muted-foreground">{{ t('compositionPanels.numbering.globalHint') }}</span>
            </span>
          </label>
          <label class="flex items-start gap-2 text-sm">
            <RadioGroupItem value="heading" class="mt-0.5" />
            <span>
              {{ t('compositionPanels.numbering.heading') }}
              <span class="block text-xs text-muted-foreground">{{ t('compositionPanels.numbering.headingHint') }}</span>
            </span>
          </label>
        </RadioGroup>
      </div>
      <Button
        size="sm"
        variant="outline"
        class="mt-3 w-full"
        :disabled="disabled"
        @click="emit('autofill', mode)"
      >
        <Wand2 class="mr-2 h-4 w-4" /> {{ t('compositionPanels.numbering.autofill') }}
      </Button>
      <p class="mt-2 text-xs text-muted-foreground">
        {{ t('compositionPanels.numbering.autofillWarning') }}
      </p>
    </template>
  </div>
</template>
