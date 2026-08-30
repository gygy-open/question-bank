<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { X, Trash2, FileText } from '@lucide/vue'
import { useQuestionBasket } from '@/composables/useQuestionBasket'
import CompositionTargetPicker from './CompositionTargetPicker.vue'
import type { Subject } from '~/types'

const props = defineProps<{
  open: boolean
  subjects?: Subject[] | null
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
}>()

const isOpen = computed({
  get: () => props.open,
  set: (v) => emit('update:open', v),
})

const { groupedBySubject, remove, clear, removeMany } = useQuestionBasket()

const subjectName = (id: number) => props.subjects?.find((s) => s.id === id)?.name ?? `学科 ${id}`

const qTypeLabels: Record<string, string> = {
  single_choice: '单选',
  multiple_choice: '多选',
  true_false: '判断',
  fill_in_the_blank: '填空',
  free_response: '解答',
}

const pickerOpen = ref(false)
const pickerSubjectId = ref<number | null>(null)
const pickerQuestionIds = ref<number[]>([])

const openPickerFor = (subjectId: number, ids: number[]) => {
  pickerSubjectId.value = subjectId
  pickerQuestionIds.value = ids
  pickerOpen.value = true
}

// 稿件加入成功后，只把这次实际提交的题目从试题篮移除（面板内容此时可能已变化）。
const onAdded = () => {
  removeMany(pickerQuestionIds.value)
}
</script>

<template>
  <Sheet v-model:open="isOpen">
    <SheetContent class="w-[420px] sm:w-[480px] flex flex-col p-0 gap-0">
      <SheetHeader class="border-b pr-12">
        <div class="flex items-start justify-between gap-2">
          <div>
            <SheetTitle>试题篮</SheetTitle>
            <SheetDescription>暂存的题目，可一键加入稿件</SheetDescription>
          </div>
          <Button
            v-if="groupedBySubject.size > 0"
            variant="ghost"
            size="sm"
            class="shrink-0 text-muted-foreground"
            @click="clear()"
          >
            清空试题篮
          </Button>
        </div>
      </SheetHeader>

      <div
        v-if="groupedBySubject.size === 0"
        class="flex-1 flex items-center justify-center text-sm text-muted-foreground"
      >
        试题篮是空的
      </div>

      <ScrollArea v-else class="flex-1 min-h-0">
        <div class="px-4 py-4">
          <div v-for="[subjectId, list] in groupedBySubject" :key="subjectId" class="mb-6 last:mb-0">
            <!-- 分组标题与操作按钮 sticky 在滚动区顶部，无需滚到底部才能操作。 -->
            <div class="sticky top-0 z-10 -mx-4 bg-background px-4 py-2">
              <div class="flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <span class="text-sm font-medium">{{ subjectName(subjectId) }}</span>
                  <span class="text-xs text-muted-foreground">{{ list.length }} 题</span>
                </div>
                <div class="flex items-center gap-1">
                  <Button size="sm" class="h-7 px-2" @click="openPickerFor(subjectId, list.map((i) => i.id))">
                    <FileText class="mr-1 h-3 w-3" />
                    加入稿件
                  </Button>
                  <Button size="sm" variant="ghost" class="h-7 px-2 text-muted-foreground" @click="clear(subjectId)">
                    <Trash2 class="mr-1 h-3 w-3" />
                    清空本组
                  </Button>
                </div>
              </div>
            </div>
            <div class="space-y-2 pt-1">
              <div
                v-for="item in list"
                :key="item.id"
                class="flex items-start justify-between gap-2 rounded-md border p-2 text-sm"
              >
                <div class="min-w-0">
                  <div class="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <Badge variant="outline" class="text-[10px] px-1">{{ qTypeLabels[item.q_type] ?? item.q_type }}</Badge>
                    <span>难度 {{ item.difficulty }}</span>
                  </div>
                  <p class="truncate">{{ item.content_preview || '（无题干文本）' }}</p>
                </div>
                <Button variant="ghost" size="icon" class="h-6 w-6 shrink-0" @click="remove(item.id)">
                  <X class="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          </div>
        </div>
      </ScrollArea>
    </SheetContent>
  </Sheet>

  <CompositionTargetPicker
    v-model:open="pickerOpen"
    :subject-id="pickerSubjectId"
    :question-ids="pickerQuestionIds"
    @added="onAdded"
  />
</template>
