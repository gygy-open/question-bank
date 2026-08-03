<script setup lang="ts">
import { ref, watch } from 'vue'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Loader2 } from 'lucide-vue-next'
import type { Question, KnowledgePoint, Subject } from '@/types'
import QuestionListItem from './QuestionListItem.vue'
import QuestionEditDialog from './QuestionEditDialog.vue'
import QuestionStructureSheet from './QuestionStructureSheet.vue'

const props = defineProps<{
  open: boolean
  questionId: number | null
  subjects?: Subject[]
  knowledgePoints?: KnowledgePoint[]
}>()

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
  (e: 'updated'): void
}>()

const { $api } = useNuxtApp()
const loading = ref(false)
const question = ref<Question | null>(null)

const editDialogOpen = ref(false)
const structureSheetOpen = ref(false)
const structureQuestionId = ref<number | null>(null)

const fetchQuestion = async (id: number) => {
  loading.value = true
  try {
    question.value = await $api<Question>(`/questions/${id}`)
  } catch (e) {
    console.error(e)
    question.value = null
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.open, props.questionId] as const,
  ([open, id]) => {
    if (open && id) fetchQuestion(id)
    else if (!open) question.value = null
  },
  { immediate: true },
)

const handleEditSuccess = async () => {
  editDialogOpen.value = false
  if (props.questionId) await fetchQuestion(props.questionId)
  emit('updated')
}

// Quick review updates the question in place.
const handleUpdate = (updated: Question) => {
  question.value = updated
  emit('updated')
}

const openStructure = (q: Question) => {
  structureQuestionId.value = q.id
  structureSheetOpen.value = true
}
</script>

<template>
  <Sheet :open="open" @update:open="(v) => emit('update:open', v)">
    <SheetContent side="right" class="w-full sm:max-w-2xl overflow-y-auto">
      <SheetHeader>
        <SheetTitle>题目详情</SheetTitle>
      </SheetHeader>

      <div class="px-4 pb-6">
        <div v-if="loading" class="flex items-center justify-center py-16">
          <Loader2 class="h-6 w-6 animate-spin text-muted-foreground" />
        </div>

        <QuestionListItem
          v-else-if="question"
          :item="question"
          mode="library"
          hide-delete
          hide-decompose
          default-expanded
          :all-knowledge-points="knowledgePoints || []"
          @edit="editDialogOpen = true"
          @update="handleUpdate"
          @view-structure="openStructure"
        />

        <div v-else class="text-center py-16 text-muted-foreground">
          题目已删除或加载失败
        </div>
      </div>
    </SheetContent>
  </Sheet>

  <QuestionEditDialog
    :open="editDialogOpen"
    :question="question"
    :knowledge-points="knowledgePoints"
    :subjects="subjects"
    mode="edit"
    @update:open="(v) => editDialogOpen = v"
    @success="handleEditSuccess"
  />

  <QuestionStructureSheet
    v-model:open="structureSheetOpen"
    :question-id="structureQuestionId"
  />
</template>
