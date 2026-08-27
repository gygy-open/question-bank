<script setup lang="ts">
import { computed } from 'vue'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Separator } from '@/components/ui/separator'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Award } from '@lucide/vue'

const props = defineProps<{
  enabled: boolean
  numberingEnabled: boolean
  disabled?: boolean
  items: { nodeId: string; number: string; score: number | null }[]
}>()

const emit = defineEmits<{
  'update:enabled': [value: boolean]
  'update-score': [nodeId: string, score: number | null]
}>()

const total = computed(() => props.items.reduce((sum, it) => sum + (it.score ?? 0), 0))

function onInput(nodeId: string, raw: string) {
  const trimmed = raw.trim()
  if (!trimmed) {
    emit('update-score', nodeId, null)
    return
  }
  const n = Number(trimmed)
  if (Number.isNaN(n)) return
  emit('update-score', nodeId, n)
}
</script>

<template>
  <div>
    <div class="flex items-center justify-between gap-2">
      <div class="flex items-center gap-2">
        <Award class="h-4 w-4 text-muted-foreground" />
        <span class="text-sm font-medium">赋分</span>
      </div>
      <TooltipProvider :delay-duration="300">
        <Tooltip>
          <TooltipTrigger as-child>
            <!-- span 包裹：禁用态 Switch 不触发原生事件，仍需靠外层元素显示 tooltip -->
            <span>
              <Switch
                :model-value="props.enabled"
                :disabled="props.disabled || !props.numberingEnabled"
                @update:model-value="emit('update:enabled', $event)"
              />
            </span>
          </TooltipTrigger>
          <TooltipContent v-if="!props.numberingEnabled">请先开启题号</TooltipContent>
        </Tooltip>
      </TooltipProvider>
    </div>
    <p class="mt-1.5 text-xs text-muted-foreground">
      开启后每道题可标注分值，需先开启题号。
    </p>

    <template v-if="props.enabled">
      <Separator class="my-3" />
      <div class="flex items-center justify-between gap-2">
        <span class="text-xs font-medium text-muted-foreground">分数分布</span>
        <span class="text-xs text-muted-foreground">合计 {{ total }} 分</span>
      </div>

      <p v-if="items.length === 0" class="mt-3 text-xs text-muted-foreground">画布中还没有题目</p>

      <div v-else class="mt-3 flex flex-wrap gap-2">
        <div
          v-for="item in items"
          :key="item.nodeId"
          class="flex w-12 flex-col items-center gap-0.5"
        >
          <span class="text-[10px] text-muted-foreground">{{ item.number || '—' }}</span>
          <Input
            type="number"
            min="0"
            max="1000"
            step="0.5"
            placeholder="—"
            class="h-7 w-12 px-1 text-center text-xs"
            :disabled="disabled"
            :model-value="item.score ?? ''"
            @update:model-value="onInput(item.nodeId, String($event))"
          />
        </div>
      </div>
    </template>
  </div>
</template>

