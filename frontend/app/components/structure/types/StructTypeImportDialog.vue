<script setup lang="ts">
/**
 * 导入元素类型:上传 JSON 文件或直接粘贴,格式与导出一致:
 *   [{ code, name, kind, parent_code, definition, examples, status, sort_order }]
 * 按 code 新增或更新;父节点可以出现在子节点之后(后端多轮解析)。整批在一个事务里,任何一条
 * 无效都整体回滚,所以这里先做基本预检,把明显的格式问题挡在提交之前。
 */
import { computed, ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Textarea } from '@/components/ui/textarea'

const props = defineProps<{
  open: boolean
  saving?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
  (e: 'submit', items: Array<Record<string, unknown>>): void
}>()

const { t } = useI18n()

const text = ref('')

const isOpen = computed({
  get: () => props.open,
  set: value => emit('update:open', value),
})

/** 预检结果:能解析出的条目,或第一条错误。 */
const parsed = computed<{ items: Array<Record<string, unknown>>, error: string | null }>(() => {
  if (!text.value.trim()) return { items: [], error: null }
  let data: unknown
  try {
    data = JSON.parse(text.value)
  } catch {
    return { items: [], error: t('structure.types.importNotJson') }
  }
  if (!Array.isArray(data)) return { items: [], error: t('structure.types.importNotArray') }
  // 每条至少要有 code 与 name;code 规则与后端一致。
  const bad = data.findIndex(item =>
    !item || typeof item !== 'object'
    || typeof (item as Record<string, unknown>).code !== 'string'
    || !/^[A-Za-z0-9_.-]{1,64}$/.test((item as Record<string, unknown>).code as string)
    || typeof (item as Record<string, unknown>).name !== 'string'
    || !((item as Record<string, unknown>).name as string).trim())
  if (bad >= 0) return { items: [], error: t('structure.types.importBadItem', { index: bad + 1 }) }
  return { items: data as Array<Record<string, unknown>>, error: null }
})

async function onFile(event: Event): Promise<void> {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (file) text.value = await file.text()
}

function submit(): void {
  if (parsed.value.items.length && !parsed.value.error) emit('submit', parsed.value.items)
}

watch(() => props.open, (value) => { if (value) text.value = '' })
</script>

<template>
  <Dialog v-model:open="isOpen">
    <DialogContent class="sm:max-w-xl">
      <DialogHeader>
        <DialogTitle>{{ t('structure.types.importTitle') }}</DialogTitle>
        <DialogDescription>{{ t('structure.types.importHint') }}</DialogDescription>
      </DialogHeader>
      <input type="file" accept=".json,application/json" class="text-sm" @change="onFile">
      <Textarea v-model="text" rows="10" class="font-mono text-xs" :placeholder="t('structure.types.importPlaceholder')" />
      <p v-if="parsed.error" class="text-sm text-destructive">{{ parsed.error }}</p>
      <p v-else-if="parsed.items.length" class="text-sm text-muted-foreground">{{ t('structure.types.importPreview', { count: parsed.items.length }) }}</p>
      <DialogFooter>
        <Button variant="outline" @click="isOpen = false">{{ t('common.cancel') }}</Button>
        <Button :disabled="!parsed.items.length || !!parsed.error || saving" @click="submit">{{ t('structure.types.import') }}</Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
