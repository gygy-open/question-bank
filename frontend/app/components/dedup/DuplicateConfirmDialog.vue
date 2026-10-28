<script setup lang="ts">
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import DuplicateCandidateList from '@/components/dedup/DuplicateCandidateList.vue'
import { type DuplicateCandidate, strongestLevel } from '@/lib/questionDedup'

const props = defineProps<{ candidates: DuplicateCandidate[] }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ (e: 'confirm'): void }>()

const { t } = useI18n()

const title = computed(() =>
  strongestLevel(props.candidates) === 'duplicate'
    ? t('questionDedup.confirm.titleDuplicate')
    : t('questionDedup.confirm.titleSimilar'),
)

const confirm = () => {
  open.value = false
  emit('confirm')
}
</script>

<template>
  <AlertDialog v-model:open="open">
    <AlertDialogContent class="sm:max-w-2xl">
      <AlertDialogHeader>
        <AlertDialogTitle>{{ title }}</AlertDialogTitle>
        <AlertDialogDescription>{{ t('questionDedup.confirm.description') }}</AlertDialogDescription>
      </AlertDialogHeader>
      <div class="max-h-[50vh] overflow-y-auto">
        <DuplicateCandidateList :candidates="candidates" />
      </div>
      <AlertDialogFooter>
        <AlertDialogCancel>{{ t('common.cancel') }}</AlertDialogCancel>
        <Button variant="destructive" @click="confirm">{{ t('questionDedup.confirm.saveAnyway') }}</Button>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>
</template>
