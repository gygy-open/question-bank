<script setup lang="ts">
/**
 * 编辑模式下的一个参数槽:名称、形态、原值(只读,来自原文)、取值范围与「确认范围」、是否可替换。
 *
 * 取值范围编辑为最小 / 最大 / 整数 / 可选值 / 说明;确认后才允许 AI 在范围内自动取值。
 * 范围被修改时自动取消确认,避免确认的是旧范围。
 */
import { computed } from 'vue'
import { Trash2 } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import MathText from '@/components/structure/MathText.vue'
import type { StructParamDomain, StructParamKind } from '~/types'

/** 编辑中的参数(owner 用所属条目的本地 uid 表示)。 */
export interface EditParam {
  uid: number
  ownerKind: 'element' | 'ask'
  ownerUid: number
  name: string
  value: string
  slot_kind: StructParamKind
  span: [number, number]
  domain: StructParamDomain | null
  domain_confirmed: boolean
  replaceable: boolean
}

const props = defineProps<{ param: EditParam, isMath: boolean }>()
const emit = defineEmits<{ (e: 'remove'): void }>()

const { t } = useI18n()

const kindOptions = computed(() =>
  (['numeric', 'symbolic', 'point', 'interval', 'expression'] as StructParamKind[]).map(value => ({
    value, label: t(`structure.params.kinds.${value}`),
  })),
)

/** 改动任何一项取值范围:写回 domain(全空时置 null),并取消确认。 */
function setDomain(key: keyof StructParamDomain, raw: string | boolean): void {
  const next: StructParamDomain = { ...(props.param.domain ?? {}) }
  if (key === 'min' || key === 'max') {
    const text = String(raw).trim()
    const value = Number(text)
    if (text === '' || Number.isNaN(value)) delete next[key]
    else next[key] = value
  } else if (key === 'integer') {
    if (raw) next.integer = true
    else delete next.integer
  } else if (key === 'values' || key === 'exclude') {
    const list = String(raw).split(/[,，]/).map(s => s.trim()).filter(Boolean)
    if (list.length) next[key] = list
    else delete next[key]
  } else {
    const text = String(raw).trim()
    if (text) next.note = text
    else delete next.note
  }
  props.param.domain = Object.keys(next).length ? next : null
  props.param.domain_confirmed = false
}
</script>

<template>
  <div class="space-y-2 rounded-md border border-dashed bg-muted/20 p-2 text-xs">
    <div class="flex flex-wrap items-center gap-2">
      <Input v-model="param.name" class="h-7 w-28 text-xs" :placeholder="t('structure.params.name')" maxlength="64" />
      <span class="text-muted-foreground">=</span>
      <MathText class="font-mono" :text="isMath ? `$${param.value}$` : param.value" />
      <NativeSelect v-model="param.slot_kind" class="h-8 w-28 text-xs">
        <NativeSelectOption v-for="option in kindOptions" :key="option.value" :value="option.value">{{ option.label }}</NativeSelectOption>
      </NativeSelect>
      <label class="flex items-center gap-1">
        <Checkbox :model-value="param.replaceable" @update:model-value="param.replaceable = $event === true" />
        {{ t('structure.params.replaceable') }}
      </label>
      <Button size="icon" variant="ghost" class="ml-auto h-6 w-6" :title="t('common.delete')" @click="emit('remove')">
        <Trash2 class="h-3.5 w-3.5" />
      </Button>
    </div>
    <div class="flex flex-wrap items-center gap-2">
      <span class="text-muted-foreground">{{ t('structure.params.domain') }}</span>
      <Input
        class="h-7 w-16 text-xs"
        :model-value="param.domain?.min ?? ''"
        :placeholder="t('structure.params.min')"
        @update:model-value="setDomain('min', String($event))"
      />
      <span>~</span>
      <Input
        class="h-7 w-16 text-xs"
        :model-value="param.domain?.max ?? ''"
        :placeholder="t('structure.params.max')"
        @update:model-value="setDomain('max', String($event))"
      />
      <label class="flex items-center gap-1">
        <Checkbox :model-value="!!param.domain?.integer" @update:model-value="setDomain('integer', $event === true)" />
        {{ t('structure.params.integer') }}
      </label>
      <Input
        class="h-7 w-32 text-xs"
        :model-value="param.domain?.values?.join(', ') ?? ''"
        :placeholder="t('structure.params.values')"
        :title="t('structure.params.valuesHint')"
        @update:model-value="setDomain('values', String($event))"
      />
      <Input
        class="h-7 min-w-32 flex-1 text-xs"
        :model-value="param.domain?.note ?? ''"
        :placeholder="t('structure.params.note')"
        @update:model-value="setDomain('note', String($event))"
      />
    </div>
    <label v-if="param.domain" class="flex items-center gap-1.5">
      <Checkbox :model-value="param.domain_confirmed" @update:model-value="param.domain_confirmed = $event === true" />
      <span :class="param.domain_confirmed ? 'text-emerald-700 dark:text-emerald-300' : 'text-amber-700 dark:text-amber-300'">
        {{ t('structure.params.confirmDomain') }}
      </span>
    </label>
  </div>
</template>
