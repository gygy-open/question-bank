<script setup lang="ts">
import { computed } from 'vue'
import type { OptionSpec, QuestionType } from '@/types'
import { Plus, Trash2 } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import AnswerEditor from '@/components/AnswerEditor.vue'
import RichEditor from '@/components/rich-editor/RichEditor.vue'
import { provideMediaSubject } from '@/composables/useMedia'
import {
  type QuestionDraft,
  createDefaultOptions,
  generateOptionId,
  hasOptionPool,
  nextOptionLabel,
  pruneAnswerOptionRef,
} from '@/lib/questionModel'

const draft = defineModel<QuestionDraft>({ required: true })
const { t } = useI18n()
provideMediaSubject(() => draft.value.subject_id)

const qType = computed<QuestionType>({
  get: () => draft.value.q_type,
  set: (value) => {
    const current = draft.value
    if (current.q_type === value) return
    current.q_type = value
    if (hasOptionPool(value) && current.options.length === 0) current.options = createDefaultOptions()
    current.answer = null
  },
})

const addOption = () => {
  const option: OptionSpec = {
    id: generateOptionId(),
    label: nextOptionLabel(draft.value.options.length),
    content: null,
  }
  draft.value.options.push(option)
}

const removeOption = (index: number) => {
  const current = draft.value
  const [removed] = current.options.splice(index, 1)
  // 重排 label（A/B/C…）并清理 answer 对被删选项的引用。
  current.options.forEach((option, i) => { option.label = nextOptionLabel(i) })
  if (removed) current.answer = pruneAnswerOptionRef(current.answer, removed.id)
}
</script>

<template>
  <div class="space-y-6">
    <div class="grid grid-cols-2 gap-4">
      <div class="space-y-2">
        <Label>{{ t('questionEditor.type') }}</Label>
        <Select v-model="qType">
          <SelectTrigger><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="single_choice">{{ t('questions.types.singleChoice') }}</SelectItem>
            <SelectItem value="multiple_choice">{{ t('questions.types.multipleChoice') }}</SelectItem>
            <SelectItem value="true_false">{{ t('questions.types.trueFalse') }}</SelectItem>
            <SelectItem value="fill_in_the_blank">{{ t('questions.types.fillInTheBlank') }}</SelectItem>
            <SelectItem value="free_response">{{ t('questions.types.freeResponse') }}</SelectItem>
            <SelectItem value="option_matching">{{ t('questions.types.optionMatching') }}</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <slot name="meta" />
      <div class="space-y-2">
        <Label>{{ t('questionItem.difficulty') }}</Label>
        <Select v-model="draft.difficulty">
          <SelectTrigger><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem v-for="level in 5" :key="level" :value="level">{{ t('questionItem.difficultyValue', { level }) }}</SelectItem>
          </SelectContent>
        </Select>
      </div>
    </div>

    <slot name="fields" />

    <div class="space-y-2">
      <Label>{{ t('questionEditor.stem') }}</Label>
      <RichEditor v-model="draft.content" :allow-blank="qType === 'fill_in_the_blank' || qType === 'option_matching'" />
    </div>

    <div v-if="hasOptionPool(qType)" class="space-y-2">
      <Label>{{ qType === 'option_matching' ? t('questionEditor.optionPool') : t('questionEditor.options') }}</Label>
      <div class="grid grid-cols-1 gap-4">
        <div v-for="(opt, optIndex) in draft.options" :key="opt.id" class="flex items-start gap-2">
          <div class="mt-0.5 flex h-9 w-8 shrink-0 items-center justify-center rounded bg-muted font-medium">{{ opt.label }}</div>
          <div class="flex-1">
            <RichEditor v-model="opt.content" :placeholder="t('questionEditor.optionPlaceholder')" />
          </div>
          <Button variant="ghost" size="icon" class="mt-0.5 h-8 w-8" :title="t('questionEditor.removeOption')" :aria-label="t('questionEditor.removeOption')" @click="removeOption(optIndex)">
            <Trash2 class="h-3 w-3" />
          </Button>
        </div>
        <Button variant="outline" class="w-full border-dashed" @click="addOption">
          <Plus class="mr-2 h-4 w-4" /> {{ t('questionEditor.addOption') }}
        </Button>
      </div>
    </div>

    <AnswerEditor
      v-model="draft.answer"
      :q-type="draft.q_type"
      :options="draft.options"
      :stem="draft.content"
    />

    <div class="space-y-2">
      <Label>{{ t('questionItem.thinking') }}</Label>
      <RichEditor v-model="draft.thinking" />
    </div>
    <div class="space-y-2">
      <Label>{{ t('questionItem.analysis') }}</Label>
      <RichEditor v-model="draft.analysis" />
    </div>
    <div class="space-y-2">
      <Label>{{ t('questionItem.summary') }}</Label>
      <RichEditor v-model="draft.summary" />
    </div>
  </div>
</template>
