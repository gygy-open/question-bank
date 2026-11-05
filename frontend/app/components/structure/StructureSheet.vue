<script setup lang="ts">
/**
 * 题干结构侧边弹出层:包装 StructurePanel,供题库列表、题目编辑弹窗等处打开。
 *
 * 契约:props open / targetType / targetId;emits update:open、changed(拆解结果变化后外层可刷新)。
 * 题目有两个标签页:「题干结构」与「解答结构」(三期);材料只有题干结构。
 */
import { computed, ref, watch } from 'vue'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import SolutionPanel from '@/components/structure/SolutionPanel.vue'
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

const tab = ref<'stem' | 'solution'>('stem')
watch(() => props.targetId, () => { tab.value = 'stem' })

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
      <div class="space-y-4 px-4 pb-6">
        <Tabs v-if="targetType === 'question'" v-model="tab">
          <TabsList>
            <TabsTrigger value="stem">{{ t('structure.solution.tabStem') }}</TabsTrigger>
            <TabsTrigger value="solution">{{ t('structure.solution.tabSolution') }}</TabsTrigger>
          </TabsList>
        </Tabs>
        <!-- 关闭时不渲染面板:避免后台轮询;再次打开时重新加载最新结果 -->
        <StructurePanel
          v-if="open && targetId != null && tab === 'stem'"
          :target-type="targetType"
          :target-id="targetId"
          @changed="emit('changed')"
        />
        <SolutionPanel
          v-if="open && targetId != null && tab === 'solution' && targetType === 'question'"
          :question-id="targetId"
          @changed="emit('changed')"
        />
      </div>
    </SheetContent>
  </Sheet>
</template>
