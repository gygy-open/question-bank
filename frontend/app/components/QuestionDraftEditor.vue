<script setup lang="ts">
import { computed } from 'vue'
import type { OptionSpec, QuestionType } from '@/types'
import { Plus, Trash2 } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import AnswerEditor from '@/components/AnswerEditor.vue'
import RichEditor from '@/components/rich-editor/RichEditor.vue'
import {
  type QuestionDraft,
  createDefaultOptions,
  generateOptionId,
  hasOptionPool,
  nextOptionLabel,
  pruneAnswerOptionRef,
} from '@/lib/questionModel'

const draft = defineModel<QuestionDraft>({ required: true })

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
        <Label>题目类型</Label>
        <Select v-model="qType">
          <SelectTrigger><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="single_choice">单选题</SelectItem>
            <SelectItem value="multiple_choice">多选题</SelectItem>
            <SelectItem value="true_false">判断题</SelectItem>
            <SelectItem value="fill_in_the_blank">填空题</SelectItem>
            <SelectItem value="free_response">解答题</SelectItem>
            <SelectItem value="option_matching">选项匹配</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <slot name="meta" />
      <div class="space-y-2">
        <Label>难度</Label>
        <Select v-model="draft.difficulty">
          <SelectTrigger><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem v-for="level in 5" :key="level" :value="level">难度 {{ level }}</SelectItem>
          </SelectContent>
        </Select>
      </div>
    </div>

    <slot name="fields" />

    <div class="space-y-2">
      <Label>题干</Label>
      <RichEditor v-model="draft.content" :allow-blank="qType === 'fill_in_the_blank' || qType === 'option_matching'" />
    </div>

    <div v-if="hasOptionPool(qType)" class="space-y-2">
      <Label>{{ qType === 'option_matching' ? '选项池（各空位共用）' : '选项' }}</Label>
      <div class="grid grid-cols-1 gap-4">
        <div v-for="(opt, optIndex) in draft.options" :key="opt.id" class="flex items-start gap-2">
          <div class="mt-0.5 flex h-9 w-8 shrink-0 items-center justify-center rounded bg-muted font-medium">{{ opt.label }}</div>
          <div class="flex-1">
            <RichEditor v-model="opt.content" placeholder="输入选项内容…" />
          </div>
          <Button variant="ghost" size="icon" class="mt-0.5 h-8 w-8" title="删除选项" aria-label="删除选项" @click="removeOption(optIndex)">
            <Trash2 class="h-3 w-3" />
          </Button>
        </div>
        <Button variant="outline" class="w-full border-dashed" @click="addOption">
          <Plus class="mr-2 h-4 w-4" /> 添加选项
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
      <Label>分析</Label>
      <RichEditor v-model="draft.thinking" />
    </div>
    <div class="space-y-2">
      <Label>解析</Label>
      <RichEditor v-model="draft.analysis" />
    </div>
    <div class="space-y-2">
      <Label>总结</Label>
      <RichEditor v-model="draft.summary" />
    </div>
  </div>
</template>
