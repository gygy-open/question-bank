<script setup lang="ts">
import { Plus, Search } from '@lucide/vue'
import type { AIModelInput } from '~/types/ai-config'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'

/** 勾选要启用的模型，并可调整“识图 / 向量”能力标记（默认按模型名推断）。 */
const { t } = useI18n()

const props = defineProps<{
  candidates: AIModelInput[]
  existingNames?: string[]
}>()
const selected = defineModel<AIModelInput[]>({ required: true })

interface Row extends AIModelInput { checked: boolean }

const rows = ref<Row[]>([])
const query = ref('')
const manualName = ref('')

watch(() => props.candidates, (list) => {
  const existing = new Set(props.existingNames ?? [])
  const prev = new Map(rows.value.map(r => [r.name, r]))
  const next: Row[] = list
    .filter(c => !existing.has(c.name))
    .map(c => prev.get(c.name) ?? { ...c, checked: false })
  // 保留用户手动添加、但不在新候选里的条目
  for (const r of prev.values()) {
    if (!next.some(x => x.name === r.name)) next.unshift(r)
  }
  rows.value = next
}, { immediate: true })

watch(rows, () => {
  selected.value = rows.value.filter(r => r.checked).map(({ checked: _c, ...m }) => m)
}, { deep: true, immediate: true })

const visibleRows = computed(() => {
  const q = query.value.trim().toLowerCase()
  return q ? rows.value.filter(r => r.name.toLowerCase().includes(q)) : rows.value
})

const toggleEmbedding = (row: Row) => {
  row.is_embedding_model = !row.is_embedding_model
  if (row.is_embedding_model) row.is_vision_capable = false
}

const addManual = () => {
  const name = manualName.value.trim()
  if (!name) return
  const hit = rows.value.find(r => r.name === name)
  if (hit) {
    hit.checked = true
  } else if (!(props.existingNames ?? []).includes(name)) {
    const lower = name.toLowerCase()
    const embedding = /embed/.test(lower)
    rows.value.unshift({
      name,
      checked: true,
      is_embedding_model: embedding,
      is_vision_capable: !embedding && /vision|vl|4o|gemini/.test(lower),
    })
  }
  manualName.value = ''
}
</script>

<template>
  <div class="space-y-3">
    <div v-if="rows.length > 6" class="relative">
      <Search class="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
      <Input v-model="query" :placeholder="t('aiModels.picker.search')" class="pl-9" />
    </div>

    <div v-if="rows.length" class="max-h-72 overflow-y-auto rounded-md border divide-y">
      <div
        v-for="row in visibleRows"
        :key="row.name"
        class="flex items-center gap-3 px-3 py-2 text-sm hover:bg-muted/50"
      >
        <Checkbox :id="`mp-${row.name}`" :model-value="row.checked" @update:model-value="v => row.checked = !!v" />
        <label :for="`mp-${row.name}`" class="flex-1 cursor-pointer font-mono text-xs break-all">{{ row.name }}</label>
        <div class="flex gap-1">
          <button
            type="button"
            class="rounded border px-1.5 py-0.5 text-[11px] transition-colors disabled:opacity-40"
            :class="row.is_vision_capable ? 'border-blue-300 bg-blue-50 text-blue-700' : 'text-muted-foreground'"
            :disabled="row.is_embedding_model"
            :aria-pressed="row.is_vision_capable"
            :title="t('aiModels.picker.visionTitle')"
            @click="row.is_vision_capable = !row.is_vision_capable"
          >{{ t('aiModels.capabilities.vision') }}</button>
          <button
            type="button"
            class="rounded border px-1.5 py-0.5 text-[11px] transition-colors"
            :class="row.is_embedding_model ? 'border-purple-300 bg-purple-50 text-purple-700' : 'text-muted-foreground'"
            :aria-pressed="row.is_embedding_model"
            :title="t('aiModels.picker.embeddingTitle')"
            @click="toggleEmbedding(row)"
          >{{ t('aiModels.capabilities.embedding') }}</button>
        </div>
      </div>
      <p v-if="!visibleRows.length" class="px-3 py-4 text-center text-xs text-muted-foreground">{{ t('aiModels.picker.noMatch') }}</p>
    </div>
    <p v-else class="text-sm text-muted-foreground">
      {{ t('aiModels.picker.noCandidates') }}
    </p>

    <div class="flex gap-2">
      <Input v-model="manualName" :placeholder="t('aiModels.picker.manualPlaceholder', { example: 'deepseek-chat' })" @keydown.enter.prevent="addManual" />
      <Button type="button" variant="outline" @click="addManual">
        <Plus class="mr-1 h-4 w-4" />{{ t('aiModels.picker.add') }}
      </Button>
    </div>
    <p class="text-xs text-muted-foreground">
      {{ t('aiModels.picker.summary', { count: selected.length }) }}
    </p>
  </div>
</template>
