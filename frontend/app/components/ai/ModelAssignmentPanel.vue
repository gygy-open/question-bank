<script setup lang="ts">
import { AlertTriangle, CheckCircle2, CircleDashed, FileText, Image as ImageIcon, Loader2, Search } from '@lucide/vue'
import type { FlatModel, Scene } from '~/lib/ai-config'
import { SCENES, sceneState } from '~/lib/ai-config'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from '@/components/ui/select'

export interface AssignmentRow {
  scene: Scene
  /** 该场景可选的模型（已按能力和启用状态过滤） */
  options: FlatModel[]
  /** 值为 null 时下拉框显示的文字，例如“不设置”或“跟随全局默认” */
  emptyLabel: string
  /** 值为 null 时实际生效的模型说明；undefined 表示 null 即“未配置” */
  fallbackLabel?: string | null
  description?: string
}

const { t } = useI18n()

const props = defineProps<{
  rows: AssignmentRow[]
  allModels: FlatModel[]
  saved: Partial<Record<Scene, number | null>>
  saving?: boolean
}>()
const value = defineModel<Partial<Record<Scene, number | null>>>({ required: true })
const emit = defineEmits<{ save: [], reset: [] }>()

const NULL = '__none__'
const ICONS = { text: FileText, vision: ImageIcon, embedding: Search }

const toSelect = (id: number | null | undefined) => (id == null ? NULL : String(id))
const setScene = (scene: Scene, v: unknown) => {
  value.value = { ...value.value, [scene]: v === NULL || v == null ? null : Number(v) }
}

const dirty = computed(() =>
  props.rows.some(r => (value.value[r.scene] ?? null) !== (props.saved[r.scene] ?? null)),
)

const findModel = (id: number | null | undefined) => props.allModels.find(m => m.id === id)

type Status = { tone: 'ok' | 'warn' | 'error', text: string }
const statusOf = (row: AssignmentRow): Status => {
  const id = value.value[row.scene] ?? null
  if (id == null) {
    if (row.fallbackLabel) return { tone: 'ok', text: t('aiModels.status.usingGlobal', { model: row.fallbackLabel }) }
    if (row.fallbackLabel === null) return { tone: 'warn', text: t('aiModels.status.globalUnset') }
    return { tone: 'warn', text: t('aiModels.status.unset') }
  }
  const state = sceneState(props.allModels, row.scene, id)
  if (state === 'ok') return { tone: 'ok', text: t('aiModels.status.ok') }
  const m = findModel(id)
  if (!m) return { tone: 'error', text: t('aiModels.status.deleted') }
  if (!m.providerActive) return { tone: 'error', text: t('aiModels.status.providerDisabled', { name: m.providerName }) }
  return { tone: 'error', text: t('aiModels.status.capabilityMismatch') }
}

/** 当前值不在可选项里（被停用/能力变化）时，仍要显示出来，否则下拉框是空白的。 */
const orphan = (row: AssignmentRow) => {
  const id = value.value[row.scene]
  if (id == null || row.options.some(o => o.id === id)) return null
  return findModel(id) ?? { id, label: t('aiModels.deletedModel', { id }) }
}

const grouped = (options: FlatModel[]) => {
  const personal = options.filter(o => o.isPersonal)
  const global = options.filter(o => !o.isPersonal)
  return personal.length && global.length
    ? [{ label: t('aiModels.groups.personal'), items: personal }, { label: t('aiModels.groups.global'), items: global }]
    : [{ label: '', items: options }]
}
</script>

<template>
  <div class="rounded-xl border bg-card">
    <div
      v-for="row in rows"
      :key="row.scene"
      class="flex flex-col gap-3 border-b px-4 py-4 last:border-b-0 sm:flex-row sm:items-center"
    >
      <div class="flex min-w-0 flex-1 gap-3">
        <div class="mt-0.5 shrink-0 rounded-md bg-muted p-2 text-muted-foreground">
          <component :is="ICONS[row.scene]" class="h-4 w-4" />
        </div>
        <div class="min-w-0">
          <div class="font-medium">{{ t(SCENES[row.scene].labelKey) }}</div>
          <p class="text-sm text-muted-foreground">{{ row.description ?? t(SCENES[row.scene].descriptionKey) }}</p>
          <p
            class="mt-1 flex items-center gap-1 text-xs"
            :class="{
              'text-green-600': statusOf(row).tone === 'ok',
              'text-amber-600': statusOf(row).tone === 'warn',
              'text-destructive': statusOf(row).tone === 'error',
            }"
          >
            <CheckCircle2 v-if="statusOf(row).tone === 'ok'" class="h-3.5 w-3.5" />
            <CircleDashed v-else-if="statusOf(row).tone === 'warn'" class="h-3.5 w-3.5" />
            <AlertTriangle v-else class="h-3.5 w-3.5" />
            {{ statusOf(row).text }}
          </p>
        </div>
      </div>

      <Select
        :model-value="toSelect(value[row.scene])"
        :disabled="saving"
        @update:model-value="v => setScene(row.scene, v)"
      >
        <SelectTrigger class="w-full sm:w-72">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem :value="NULL">{{ row.emptyLabel }}</SelectItem>
          <SelectItem v-if="orphan(row)" :value="String(orphan(row)!.id)" disabled>
            {{ t('aiModels.unavailablePrefix') }}{{ orphan(row)!.label }}
          </SelectItem>
          <SelectGroup v-for="g in grouped(row.options)" :key="g.label">
            <SelectLabel v-if="g.label">{{ g.label }}</SelectLabel>
            <SelectItem v-for="m in g.items" :key="m.id" :value="String(m.id)">{{ m.label }}</SelectItem>
          </SelectGroup>
          <div v-if="!row.options.length" class="px-2 py-1.5 text-xs text-muted-foreground">
            {{ t('aiModels.noOptions', { scene: t(SCENES[row.scene].labelKey) }) }}
          </div>
        </SelectContent>
      </Select>
    </div>

    <div v-if="dirty" class="flex items-center justify-end gap-2 rounded-b-xl border-t bg-amber-50/60 px-4 py-2.5 dark:bg-amber-950/20">
      <span class="mr-auto text-sm text-amber-700 dark:text-amber-400">{{ t('aiModels.unsaved') }}</span>
      <Button variant="ghost" size="sm" :disabled="saving" @click="emit('reset')">{{ t('aiModels.revert') }}</Button>
      <Button size="sm" :disabled="saving" @click="emit('save')">
        <Loader2 v-if="saving" class="mr-2 h-4 w-4 animate-spin" />{{ t('common.save') }}
      </Button>
    </div>
  </div>
</template>
