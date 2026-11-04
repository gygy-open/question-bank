<script setup lang="ts">
/**
 * 题干结构侧边弹出层:包装 StructurePanel,供题库列表、题目编辑弹窗等处打开。
 *
 * 契约:props open / targetType / targetId;emits update:open、changed(拆解结果变化后外层可刷新)。
 */
import { computed } from 'vue'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import StructurePanel from '@/components/structure/StructurePanel.vue'
import type { StructTargetType } from '~/types'

const props = defineProps<{
  open: boolean
  targetType: StructTargetType
  targetId: number | null
}>()

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
  (e: 'changed'): void
}>()

const { t } = useI18n()

const isOpen = computed({
  get: () => props.open,
  set: value => emit('update:open', value),
})
</script>

<template>
  <Sheet v-model:open="isOpen">
    <SheetContent class="w-full overflow-y-auto sm:max-w-3xl">
      <SheetHeader>
        <SheetTitle>{{ t('structure.title') }}</SheetTitle>
        <SheetDescription>{{ t('structure.panel.description') }}</SheetDescription>
      </SheetHeader>
      <div class="px-4 pb-6">
        <!-- 关闭时不渲染面板:避免后台轮询;再次打开时重新加载最新结果 -->
        <StructurePanel
          v-if="open && targetId != null"
          :target-type="targetType"
          :target-id="targetId"
          @changed="emit('changed')"
        />
      </div>
    </SheetContent>
  </Sheet>
</template>
