<script setup lang="ts">
/**
 * 元素类型选择器(题库筛选、拆解编辑、类型管理共用)。
 *
 * - 多选(multiple):v-model 为类型 id 数组,用于题库筛选;
 * - 单选:v-model 为类型 id 或 null,用于给条件 / 设问选类型、给类型选上级。
 * 选项按类型树缩进展示,可搜索;默认只列出启用的类型。
 */
import { computed, ref } from 'vue'
import { Check, ChevronsUpDown, Shapes } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Command, CommandEmpty, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'
import { buildStructTypeTree, domainClasses, flattenStructTypeTree } from '@/lib/structure'
import type { StructType, StructTypeKind } from '~/types'

const props = withDefaults(defineProps<{
  /** 学科的全部类型(扁平列表)。 */
  types: StructType[]
  /** 多选时为 id 数组,单选时为 id 或 null。 */
  modelValue: number[] | number | null
  multiple?: boolean
  /** 只列出某一类(条件 / 设问)。 */
  kind?: StructTypeKind
  /** 是否也列出待确认、已停用的类型(类型管理里选上级时需要)。 */
  includeInactive?: boolean
  /** 不可选的类型 id(例如移动时排除自身及子孙)。 */
  disabledIds?: number[]
  placeholder?: string
  /** 单选时是否提供「不选」项。 */
  allowNone?: boolean
  triggerClass?: string
}>(), {
  multiple: false,
  includeInactive: false,
  allowNone: true,
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: number[] | number | null): void
}>()

const { t } = useI18n()
const open = ref(false)

// 可选项:按树展开,带缩进深度。
const options = computed(() => {
  const visible = props.includeInactive ? props.types : props.types.filter(item => item.status === 'active')
  return flattenStructTypeTree(buildStructTypeTree(visible, props.kind))
})

const selectedIds = computed<number[]>(() => {
  if (Array.isArray(props.modelValue)) return props.modelValue
  return props.modelValue != null ? [props.modelValue] : []
})

const byId = computed(() => new Map(props.types.map(item => [item.id, item])))

// 触发按钮上的文字:单选显示类型名,多选显示数量。
const label = computed(() => {
  if (!selectedIds.value.length) return props.placeholder ?? t('structure.typeSelect.placeholder')
  if (!props.multiple) return byId.value.get(selectedIds.value[0]!)?.name ?? ''
  return t('structure.typeSelect.selected', { count: selectedIds.value.length })
})

const toggle = (id: number) => {
  if (props.disabledIds?.includes(id)) return
  if (props.multiple) {
    const next = selectedIds.value.includes(id)
      ? selectedIds.value.filter(value => value !== id)
      : [...selectedIds.value, id]
    emit('update:modelValue', next)
    return
  }
  emit('update:modelValue', id)
  open.value = false
}

const clear = () => {
  emit('update:modelValue', props.multiple ? [] : null)
  if (!props.multiple) open.value = false
}
</script>

<template>
  <Popover v-model:open="open">
    <PopoverTrigger as-child>
      <Button
        variant="outline"
        role="combobox"
        :aria-expanded="open"
        :class="cn('h-9 w-full justify-between font-normal', triggerClass)"
      >
        <span class="flex items-center gap-2 truncate">
          <Shapes class="h-4 w-4 shrink-0 opacity-50" />
          <span class="truncate" :class="selectedIds.length ? '' : 'text-muted-foreground'">{{ label }}</span>
        </span>
        <ChevronsUpDown class="ml-2 h-4 w-4 shrink-0 opacity-50" />
      </Button>
    </PopoverTrigger>
    <PopoverContent class="w-[320px] p-0" align="start">
      <Command>
        <CommandInput :placeholder="t('structure.typeSelect.search')" />
        <CommandList class="max-h-[360px] overflow-y-auto">
          <CommandEmpty>{{ t('structure.typeSelect.empty') }}</CommandEmpty>
          <CommandItem
            v-if="!multiple && allowNone"
            value="__none__"
            @select="clear"
          >
            <span class="text-muted-foreground">{{ t('structure.typeSelect.none') }}</span>
          </CommandItem>
          <CommandItem
            v-for="option in options"
            :key="option.id"
            :value="`${option.name} ${option.code} #${option.id}`"
            :disabled="disabledIds?.includes(option.id)"
            @select="toggle(option.id)"
          >
            <span :style="{ paddingLeft: `${option.depth * 14}px` }" class="flex min-w-0 items-center gap-2">
              <span
                :class="cn(
                  'flex h-4 w-4 shrink-0 items-center justify-center rounded-sm border border-primary',
                  selectedIds.includes(option.id) ? 'bg-primary text-primary-foreground' : 'opacity-50 [&_svg]:invisible',
                )"
              >
                <Check class="h-3 w-3" />
              </span>
              <span :class="cn('h-2 w-2 shrink-0 rounded-full', domainClasses(types, option.id).dot)" />
              <span class="truncate">{{ option.name }}</span>
              <span v-if="option.status !== 'active'" class="shrink-0 text-xs text-muted-foreground">
                {{ t(`structure.typeStatuses.${option.status}`) }}
              </span>
            </span>
          </CommandItem>
        </CommandList>
        <div v-if="multiple" class="flex items-center justify-between border-t p-2">
          <span class="text-xs text-muted-foreground">{{ t('structure.typeSelect.selected', { count: selectedIds.length }) }}</span>
          <Button v-if="selectedIds.length" variant="ghost" size="sm" class="h-auto px-2 py-1 text-xs" @click="clear">
            {{ t('common.clear') }}
          </Button>
        </div>
      </Command>
    </PopoverContent>
  </Popover>
</template>
