<script setup lang="ts">
import { ref } from 'vue'
import { Button } from '@/components/ui/button'
import { Card, CardHeader, CardTitle, CardDescription, CardFooter } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import { Loader2, CheckCircle2, XCircle, FileText } from '@lucide/vue'
import { toast } from 'vue-sonner'
import QuestionListItem from '@/components/QuestionListItem.vue'

const props = defineProps<{
  questionIds: number[]
}>()

const emit = defineEmits(['confirmed', 'rejected'])

const { t } = useI18n()

const { $api } = useNuxtApp()
const isOpen = ref(false)
const loading = ref(false)
const questions = ref<any[]>([])
const processing = ref(false)
const processed = ref(false)
const processedAction = ref<'approved' | 'rejected' | null>(null)

const fetchQuestions = async () => {
  loading.value = true
  try {
    const data = await $api('/questions', {
      query: {
        ids: props.questionIds,
        size: 100
      }
    })
    questions.value = data.items
  } catch (e) {
    toast.error(t('batchImport.loadFailed'))
  } finally {
    loading.value = false
  }
}

const openDialog = () => {
  isOpen.value = true
  if (questions.value.length === 0) {
    fetchQuestions()
  }
}

const handleConfirm = async () => {
  processing.value = true
  try {
    await $api('/questions/batch-confirm', {
      method: 'POST',
      body: {
        question_ids: props.questionIds,
        action: 'approve'
      }
    })
    processed.value = true
    processedAction.value = 'approved'
    toast.success(t('batchImport.imported'))
    emit('confirmed')
    isOpen.value = false
  } catch (e) {
    toast.error(t('batchImport.confirmFailed'))
  } finally {
    processing.value = false
  }
}

const handleReject = async () => {
  processing.value = true
  try {
    await $api('/questions/batch-confirm', {
      method: 'POST',
      body: {
        question_ids: props.questionIds,
        action: 'reject'
      }
    })
    processed.value = true
    processedAction.value = 'rejected'
    toast.info(t('batchImport.rejected'))
    emit('rejected')
    isOpen.value = false
  } catch (e) {
    toast.error(t('batchImport.rejectFailed'))
  } finally {
    processing.value = false
  }
}
</script>

<template>
  <div class="my-4">
    <Card v-if="!processed" class="w-full max-w-md border-blue-200 bg-blue-50 dark:bg-blue-950/20 dark:border-blue-800">
      <CardHeader class="pb-2">
        <CardTitle class="text-base flex items-center gap-2">
          <FileText class="w-4 h-4 text-blue-600" />
          {{ t('batchImport.title') }}
        </CardTitle>
        <CardDescription>
          {{ t('batchImport.description', { count: questionIds.length }) }}
        </CardDescription>
      </CardHeader>
      <CardFooter>
        <Button @click="openDialog" variant="default" size="sm" class="w-full">
          {{ t('batchImport.review') }}
        </Button>
      </CardFooter>
    </Card>

    <div v-else class="flex items-center gap-2 text-sm p-4 rounded-lg border"
      :class="processedAction === 'approved' ? 'bg-green-50 border-green-200 text-green-700' : 'bg-gray-50 border-gray-200 text-gray-500'">
      <CheckCircle2 v-if="processedAction === 'approved'" class="w-4 h-4" />
      <XCircle v-else class="w-4 h-4" />
      <span>
        {{ processedAction === 'approved' ? t('batchImport.importedDone') : t('batchImport.rejectedDone') }}
      </span>
    </div>

    <Dialog :open="isOpen" @update:open="isOpen = $event">
      <DialogContent class="max-w-3xl max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>{{ t('batchImport.dialogTitle') }}</DialogTitle>
          <DialogDescription>
            {{ t('batchImport.dialogDescription', { count: questions.length }) }}
          </DialogDescription>
        </DialogHeader>
        
        <div class="flex-1 overflow-y-auto pr-4 -mr-4 min-h-0">
          <div v-if="loading" class="flex justify-center py-8">
            <Loader2 class="w-8 h-8 animate-spin text-muted-foreground" />
          </div>
          <div v-else class="space-y-6 py-4">
            <div v-for="(q, index) in questions" :key="q.id">
              <QuestionListItem 
                :item="q" 
                :index="index" 
                mode="library"
                class="border rounded-lg p-4 bg-card"
              />
            </div>
          </div>
        </div>

        <DialogFooter class="gap-2 sm:gap-0">
          <Button variant="outline" @click="handleReject" :disabled="processing">
            {{ t('batchImport.reject') }}
          </Button>
          <Button @click="handleConfirm" :disabled="processing">
            <Loader2 v-if="processing" class="w-4 h-4 mr-2 animate-spin" />
            {{ t('batchImport.confirm') }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
