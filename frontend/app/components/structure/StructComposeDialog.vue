<script setup lang="ts">
/**
 * 命题篮对话框(规格 §12.3 N4):查看、移除篮中的条件 / 设问 / 元素组,选择题型并补充说明,
 * 交给 AI 写出一道新题;新题经结构一致性校验与解题校验后存为草稿题,与每道来源题以「拼装」关联。
 */
import { computed, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import { Loader2, Trash2 } from '@lucide/vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { Textarea } from '@/components/ui/textarea'
import MathText from '@/components/structure/MathText.vue'
import StructComposeJobStatus from '@/components/structure/StructComposeJobStatus.vue'
import { getApiErrorDetail } from '@/lib/apiErrors'
import { questionTypeLabelKey } from '@/lib/answerFormat'

const open = defineModel<boolean>('open', { default: false })

const { t } = useI18n()
const api = useStructure()
const basket = useComposeBasket()

const qType = ref('free_response')
const note = ref('')
const submitting = ref(false)
const jobId = ref<number | null>(null)

const kindLabel = computed(() => ({
  element: t('structure.condition'),
  ask: t('structure.ask'),
  group: t('structure.groups.group'),
}))
const typeOptions = computed(() => ['single_choice', 'multiple_choice', 'true_false', 'fill_in_the_blank', 'free_response'].map(value => ({
  value, label: t(questionTypeLabelKey(value) ?? value),
})))
const ready = computed(() =>
  basket.items.value.some(i => i.kind !== 'ask') && basket.items.value.some(i => i.kind === 'ask'),
)

async function submit(): Promise<void> {
  submitting.value = true
  try {
    const ids = (kind: string) => basket.items.value.filter(i => i.kind === kind).map(i => i.id)
    jobId.value = (await api.compose({
      element_ids: ids('element'),
      ask_ids: ids('ask'),
      group_ids: ids('group'),
      q_type: qType.value,
      note: note.value.trim() || null,
    })).job_id
  } catch (e) {
    toast.error(t('structure.compose.failed'), { description: getApiErrorDetail(e, '') })
  } finally {
    submitting.value = false
  }
}

watch(open, (value) => {
  if (value) jobId.value = null
})
</script>

<template>
  <Dialog v-model:open="open">
    <DialogContent class="sm:max-w-2xl">
      <DialogHeader>
        <DialogTitle>{{ t('structure.compose.title') }}</DialogTitle>
        <DialogDescription>{{ t('structure.compose.description') }}</DialogDescription>
      </DialogHeader>
      <div v-if="jobId == null" class="space-y-4">
        <p v-if="!basket.items.value.length" class="py-4 text-center text-sm text-muted-foreground">{{ t('structure.compose.empty') }}</p>
        <ul class="max-h-72 space-y-1.5 overflow-y-auto">
          <li v-for="item in basket.items.value" :key="`${item.kind}-${item.id}`" class="flex items-start gap-2 rounded-md border px-3 py-2 text-sm">
            <Badge variant="secondary" class="shrink-0 font-normal">{{ kindLabel[item.kind] }}</Badge>
            <MathText class="min-w-0 flex-1" :text="item.content" />
            <span class="shrink-0 text-xs text-muted-foreground">#{{ item.question_id }}</span>
            <Button size="icon" variant="ghost" class="h-6 w-6 shrink-0" :title="t('common.delete')" @click="basket.remove(item.kind, item.id)">
              <Trash2 class="h-3.5 w-3.5" />
            </Button>
          </li>
        </ul>
        <div class="flex flex-wrap items-center gap-3">
          <span class="text-sm">{{ t('structure.compose.qType') }}</span>
          <NativeSelect v-model="qType" class="h-9 w-36">
            <NativeSelectOption v-for="option in typeOptions" :key="option.value" :value="option.value">{{ option.label }}</NativeSelectOption>
          </NativeSelect>
        </div>
        <Textarea v-model="note" rows="2" :placeholder="t('structure.compose.notePlaceholder')" />
        <p v-if="basket.items.value.length && !ready" class="text-xs text-amber-700 dark:text-amber-300">{{ t('structure.compose.needBoth') }}</p>
      </div>
      <StructComposeJobStatus v-else :job-id="jobId" @open="open = false" />
      <DialogFooter>
        <Button v-if="jobId == null && basket.items.value.length" variant="ghost" class="mr-auto" @click="basket.clear()">{{ t('structure.compose.clear') }}</Button>
        <Button variant="outline" @click="open = false">{{ jobId == null ? t('common.cancel') : t('common.close') }}</Button>
        <Button v-if="jobId == null" :disabled="!ready || submitting" @click="submit">
          <Loader2 v-if="submitting" class="mr-2 h-4 w-4 animate-spin" />{{ t('structure.compose.submit') }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
