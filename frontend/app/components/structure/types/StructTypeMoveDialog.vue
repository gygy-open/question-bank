<script setup lang="ts">
/**
 * 移动 / 合并元素类型的对话框。
 *
 * - 移动:选新的上级(同一类:条件或设问),不能选自身及子孙(否则形成环);
 * - 合并:选另一个同类类型,把本类型的引用和子类型迁过去,然后删除本类型。
 */
import { computed, ref, watch } from 'vue'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import StructTypeSelect from '@/components/structure/StructTypeSelect.vue'
import { structTypeDescendants } from '@/lib/structure'
import type { StructType } from '~/types'

const props = defineProps<{
  open: boolean
  mode: 'move' | 'merge'
  /** 被移动 / 合并的类型。 */
  source: StructType | null
  types: StructType[]
  saving?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
  (e: 'submit', targetId: number): void
}>()

const { t } = useI18n()

const targetId = ref<number | null>(null)

const isOpen = computed({
  get: () => props.open,
  set: value => emit('update:open', value),
})

/**
 * 不可选的类型:
 * - 移动时:自身及全部子孙(挂到自己下面会形成环);当前上级(移动无意义);
 * - 合并时:自身及全部子孙(合并进自己的子孙同样会形成环)。
 */
const disabledIds = computed(() => {
  if (!props.source) return []
  const blocked = structTypeDescendants(props.types, [props.source.id])
  if (props.mode === 'move' && props.source.parent_id != null) blocked.add(props.source.parent_id)
  return [...blocked]
})

watch(() => props.open, (value) => { if (value) targetId.value = null })

function submit(): void {
  if (targetId.value != null) emit('submit', targetId.value)
}
</script>

<template>
  <Dialog v-model:open="isOpen">
    <DialogContent class="sm:max-w-md">
      <DialogHeader>
        <DialogTitle>{{ mode === 'move' ? t('structure.types.moveTitle', { name: source?.name ?? '' }) : t('structure.types.mergeTitle', { name: source?.name ?? '' }) }}</DialogTitle>
        <DialogDescription>{{ mode === 'move' ? t('structure.types.moveHint') : t('structure.types.mergeHint') }}</DialogDescription>
      </DialogHeader>
      <StructTypeSelect
        v-model="targetId"
        :types="types"
        :kind="source?.kind"
        include-inactive
        :allow-none="false"
        :disabled-ids="disabledIds"
        :placeholder="mode === 'move' ? t('structure.types.pickParent') : t('structure.types.pickTarget')"
      />
      <DialogFooter>
        <Button variant="outline" @click="isOpen = false">{{ t('common.cancel') }}</Button>
        <Button :variant="mode === 'merge' ? 'destructive' : 'default'" :disabled="targetId == null || saving" @click="submit">
          {{ mode === 'move' ? t('structure.types.move') : t('structure.types.merge') }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
