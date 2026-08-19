<script setup lang="ts">
import { computed, ref } from 'vue'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import {
  FIELD_ORDER, FIELD_LABEL, FIELD_HINT, REGION_LABEL, DOCUMENT_PRESETS, makeDisplay,
} from '@/lib/displayPolicy'
import type { DisplayPolicy, DisplayField, DisplayRegion, NumberingPolicy, ScoringPolicy } from '~/types'

const props = defineProps<{
  modelValue: DisplayPolicy | null | undefined
  numbering?: NumberingPolicy | null
  scoring?: ScoringPolicy | null
}>()
const emit = defineEmits<{
  'update:modelValue': [DisplayPolicy]
  'update:numbering': [NumberingPolicy]
  'update:scoring': [ScoringPolicy]
}>()

const REGIONS: DisplayRegion[] = ['inline', 'appendix', 'hidden']

const regionOf = (field: DisplayField): DisplayRegion =>
  props.modelValue?.fields?.[field]?.region ?? 'hidden'

const setRegion = (field: DisplayField, region: DisplayRegion | undefined) => {
  if (!region) return
  const base = props.modelValue?.fields ?? {}
  emit('update:modelValue', {
    v: props.modelValue?.v ?? 1,
    fields: { ...base, [field]: { region } },
  })
}

// 整列一键设置: 把 5 个字段的落位全部改成同一个区域
const setColumn = (region: DisplayRegion) => {
  const fields = Object.fromEntries(FIELD_ORDER.map((f) => [f, { region }])) as DisplayPolicy['fields']
  emit('update:modelValue', { v: props.modelValue?.v ?? 1, fields })
}

// 预设只是一次性动作, 选完即复位, 不代表持久选中状态
const presetValue = ref('')
const applyPreset = (value: string) => {
  const preset = DOCUMENT_PRESETS.find((p) => p.value === value)
  if (preset) emit('update:modelValue', makeDisplay(preset.regions))
  presetValue.value = ''
}

const autoNumber = computed(() => props.numbering?.auto !== false)
const numberingScope = computed(() => props.numbering?.scope ?? 'section')

const setAutoNumber = (v: string | undefined) => {
  if (!v) return
  emit('update:numbering', { ...props.numbering, auto: v === 'on' })
}
const setNumberingScope = (v: string | undefined) => {
  if (!v) return
  emit('update:numbering', { ...props.numbering, scope: v as 'section' | 'document' | 'outline' })
}

const scoringEnabled = computed(() => props.scoring?.enabled !== false)
const setScoringEnabled = (v: string | undefined) => {
  if (!v) return
  emit('update:scoring', { ...props.scoring, enabled: v === 'on' })
}
</script>

<template>
  <div class="space-y-3">
    <div class="flex items-center justify-between gap-2">
      <p class="text-xs text-muted-foreground">这些内容显示在哪里，题目可单独覆盖</p>
      <Select :model-value="presetValue" @update:model-value="(v) => applyPreset(String(v))">
        <SelectTrigger class="h-7 w-24 text-xs">
          <SelectValue placeholder="快捷预设" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem v-for="p in DOCUMENT_PRESETS" :key="p.value" :value="p.value">
            {{ p.label }}
          </SelectItem>
        </SelectContent>
      </Select>
    </div>

    <!-- 区域表头 + 整列批量设置 -->
    <div class="flex items-center gap-2 text-xs text-muted-foreground">
      <span class="w-9 shrink-0" />
      <div class="flex flex-1 gap-0.5">
        <button
          v-for="r in REGIONS"
          :key="r"
          class="flex-1 rounded px-1 py-0.5 hover:bg-muted hover:text-foreground"
          :title="`全部设为${REGION_LABEL[r]}`"
          @click="setColumn(r)"
        >
          全部{{ REGION_LABEL[r] }}
        </button>
      </div>
    </div>

    <div class="space-y-2">
      <div v-for="f in FIELD_ORDER" :key="f" class="flex items-center gap-2">
        <Tooltip>
          <TooltipTrigger as-child>
            <span class="w-9 shrink-0 cursor-help text-xs text-muted-foreground underline decoration-dotted underline-offset-2">
              {{ FIELD_LABEL[f] }}
            </span>
          </TooltipTrigger>
          <TooltipContent>{{ FIELD_HINT[f] }}</TooltipContent>
        </Tooltip>
        <ToggleGroup
          type="single"
          :model-value="regionOf(f)"
          class="flex-1"
          :spacing="0"
          variant="outline"
          size="sm"
          @update:model-value="(v) => setRegion(f, v as DisplayRegion | undefined)"
        >
          <ToggleGroupItem v-for="r in REGIONS" :key="r" :value="r" class="flex-1 text-xs">
            {{ REGION_LABEL[r] }}
          </ToggleGroupItem>
        </ToggleGroup>
      </div>
    </div>

    <div class="space-y-2 border-t pt-3">
      <p class="text-xs text-muted-foreground">题号</p>
      <div class="flex items-center gap-2">
        <span class="w-16 shrink-0 text-xs text-muted-foreground">自动编号</span>
        <ToggleGroup
          type="single"
          :model-value="autoNumber ? 'on' : 'off'"
          class="flex-1"
          :spacing="0"
          variant="outline"
          size="sm"
          @update:model-value="(v) => setAutoNumber(v as string | undefined)"
        >
          <ToggleGroupItem value="on" class="flex-1 text-xs">开</ToggleGroupItem>
          <ToggleGroupItem value="off" class="flex-1 text-xs">关</ToggleGroupItem>
        </ToggleGroup>
      </div>
      <div v-if="autoNumber" class="flex items-center gap-2">
        <span class="w-16 shrink-0 text-xs text-muted-foreground">编号范围</span>
        <ToggleGroup
          type="single"
          :model-value="numberingScope"
          class="flex-1"
          :spacing="0"
          variant="outline"
          size="sm"
          @update:model-value="(v) => setNumberingScope(v as string | undefined)"
        >
          <ToggleGroupItem value="section" class="flex-1 text-xs" title="遇到标题就把题号重新从 1 开始数">
            分节
          </ToggleGroupItem>
          <ToggleGroupItem value="document" class="flex-1 text-xs" title="不管标题, 全文题号连续数下去">
            连续
          </ToggleGroupItem>
          <ToggleGroupItem value="outline" class="flex-1 text-xs" title="按标题 2~4 级嵌套生成 1.1、1.2、2.1 这样的题号">
            分级
          </ToggleGroupItem>
        </ToggleGroup>
      </div>
    </div>

    <div class="space-y-2 border-t pt-3">
      <p class="text-xs text-muted-foreground">赋分</p>
      <div class="flex items-center gap-2">
        <span class="w-16 shrink-0 text-xs text-muted-foreground">启用赋分</span>
        <ToggleGroup
          type="single"
          :model-value="scoringEnabled ? 'on' : 'off'"
          class="flex-1"
          :spacing="0"
          variant="outline"
          size="sm"
          @update:model-value="(v) => setScoringEnabled(v as string | undefined)"
        >
          <ToggleGroupItem value="on" class="flex-1 text-xs">开</ToggleGroupItem>
          <ToggleGroupItem value="off" class="flex-1 text-xs" title="隐藏分值输入, 导出时不打印分值 (已录入的分数不会被清除)">关</ToggleGroupItem>
        </ToggleGroup>
      </div>
    </div>
  </div>
</template>
