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

const mode = ref<NumberingMode>('global')
</script>

<template>
  <div class="rounded-lg border bg-card p-4">
    <div class="flex items-center justify-between gap-2">
      <div class="flex items-center gap-2">
        <ListOrdered class="h-4 w-4 text-muted-foreground" />
        <span class="text-sm font-medium">题号</span>
      </div>
      <Switch
        :model-value="enabled"
        :disabled="disabled"
        @update:model-value="emit('update:enabled', $event)"
      />
    </div>
    <p class="mt-1.5 text-xs text-muted-foreground">
      开启后每道题前显示题号，可逐题手动修改。
    </p>

    <template v-if="enabled">
      <div class="mt-4 space-y-2">
        <Label class="text-xs text-muted-foreground">自动填充方式</Label>
        <RadioGroup v-model="mode" class="gap-2">
          <label class="flex items-start gap-2 text-sm">
            <RadioGroupItem value="global" class="mt-0.5" />
            <span>
              全局顺序
              <span class="block text-xs text-muted-foreground">按题目顺序 1、2、3…</span>
            </span>
          </label>
          <label class="flex items-start gap-2 text-sm">
            <RadioGroupItem value="heading" class="mt-0.5" />
            <span>
              按标题分组
              <span class="block text-xs text-muted-foreground">以 H2 标题分组，1.1、2.1…</span>
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
        <Wand2 class="mr-2 h-4 w-4" /> 自动填充题号
      </Button>
      <p class="mt-2 text-xs text-muted-foreground">
        自动填充为一次性操作，会覆盖所有已有题号。
      </p>
    </template>
  </div>
</template>
