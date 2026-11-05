<script setup lang="ts">
/**
 * 新建 / 编辑元素类型的对话框:名称、编码(仅新建)、定义、正反例、状态。
 *
 * 定义与正反例让 AI 和不同老师对同一类型理解一致:拆解提示词里会带上「定义」。
 */
import { computed, ref, watch } from 'vue'
import { Plus, Trash2 } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { Textarea } from '@/components/ui/textarea'
import type { StructTypeFormValue } from '@/lib/structure'
import KnowledgePointSelector from '@/components/KnowledgePointSelector.vue'
import type { KnowledgePoint, StructType, StructTypeKind, StructTypeStatus } from '~/types'

const props = defineProps<{
  open: boolean
  /** 编辑时传入现有类型;新建时为 null。 */
  initial: StructType | null
  /** 新建时的上级名称(用于标题提示)。 */
  parentName?: string | null
  saving?: boolean
  /** 类型属于哪一类:方法类型可以设权重。 */
  kind?: StructTypeKind
  /** 本学科的知识点(用于映射,规格 §12.3 N8)。 */
  knowledgePoints?: KnowledgePoint[]
}>()

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
  (e: 'submit', value: StructTypeFormValue): void
}>()

const { t } = useI18n()

// region 状态

const name = ref('')
const code = ref('')
const definition = ref('')
const examples = ref<Array<{ text: string, positive: boolean }>>([])
const status = ref<StructTypeStatus>('active')
const weight = ref(1)
const knowledgePointIds = ref<number[]>([])

// endregion

// region 计算属性

const isOpen = computed({
  get: () => props.open,
  set: value => emit('update:open', value),
})

const isEdit = computed(() => props.initial != null)

// 编码只允许字母数字与 . _ -,与后端校验一致;留空由后端按名称生成。
const codeInvalid = computed(() => !!code.value && !/^[A-Za-z0-9_.-]{1,64}$/.test(code.value))
const weightInvalid = computed(() => !(Number(weight.value) > 0 && Number(weight.value) <= 100))
const canSubmit = computed(() => !!name.value.trim() && !codeInvalid.value && !weightInvalid.value && !props.saving)

const statusOptions = computed(() => (['active', 'candidate', 'deprecated'] as StructTypeStatus[])
  .map(value => ({ value, label: t(`structure.typeStatuses.${value}`) })))

// endregion

// region 事件处理

function addExample(positive: boolean): void {
  examples.value.push({ text: '', positive })
}

function submit(): void {
  if (!canSubmit.value) return
  emit('submit', {
    name: name.value.trim(),
    code: code.value.trim(),
    definition: definition.value.trim(),
    // 空示例不提交。
    examples: examples.value.filter(item => item.text.trim()).map(item => ({ text: item.text.trim(), positive: item.positive })),
    status: status.value,
    weight: Number(weight.value),
    knowledge_point_ids: knowledgePointIds.value,
  })
}

// endregion

// 每次打开时按传入的类型重置表单。
watch(() => props.open, (value) => {
  if (!value) return
  name.value = props.initial?.name ?? ''
  code.value = props.initial?.code ?? ''
  definition.value = props.initial?.definition ?? ''
  examples.value = (props.initial?.examples ?? []).map(item => ({ text: item.text, positive: item.positive !== false }))
  status.value = props.initial?.status ?? 'active'
  weight.value = props.initial?.weight ?? 1
  knowledgePointIds.value = [...(props.initial?.knowledge_point_ids ?? [])]
}, { immediate: true })
</script>

<template>
  <Dialog v-model:open="isOpen">
    <DialogContent class="sm:max-w-lg">
      <DialogHeader>
        <DialogTitle>{{ isEdit ? t('structure.types.editTitle') : t('structure.types.createTitle') }}</DialogTitle>
        <DialogDescription v-if="!isEdit && parentName">{{ t('structure.types.createUnder', { name: parentName }) }}</DialogDescription>
      </DialogHeader>

      <div class="space-y-4">
        <div class="space-y-1.5">
          <Label>{{ t('structure.types.name') }}</Label>
          <Input v-model="name" :placeholder="t('structure.types.namePlaceholder')" />
        </div>
        <div v-if="!isEdit" class="space-y-1.5">
          <Label>{{ t('structure.types.code') }}</Label>
          <Input v-model="code" class="font-mono" :placeholder="t('structure.types.codePlaceholder')" />
          <p v-if="codeInvalid" class="text-xs text-destructive">{{ t('structure.types.codeInvalid') }}</p>
        </div>
        <div class="space-y-1.5">
          <Label>{{ t('structure.types.definition') }}</Label>
          <Textarea v-model="definition" rows="3" :placeholder="t('structure.types.definitionPlaceholder')" />
        </div>
        <div class="space-y-1.5">
          <div class="flex items-center justify-between">
            <Label>{{ t('structure.types.examples') }}</Label>
            <div class="flex gap-1">
              <Button size="sm" variant="ghost" class="h-7" @click="addExample(true)"><Plus class="mr-1 h-3.5 w-3.5" />{{ t('structure.types.positive') }}</Button>
              <Button size="sm" variant="ghost" class="h-7" @click="addExample(false)"><Plus class="mr-1 h-3.5 w-3.5" />{{ t('structure.types.negative') }}</Button>
            </div>
          </div>
          <div v-for="(example, index) in examples" :key="index" class="flex items-center gap-2">
            <label class="flex shrink-0 items-center gap-1 text-xs text-muted-foreground">
              <Checkbox :model-value="example.positive" @update:model-value="example.positive = $event === true" />
              {{ t('structure.types.positive') }}
            </label>
            <Input v-model="example.text" class="h-8" :placeholder="t('structure.types.examplePlaceholder')" />
            <Button size="icon" variant="ghost" class="h-8 w-8 shrink-0" @click="examples.splice(index, 1)"><Trash2 class="h-4 w-4" /></Button>
          </div>
          <p v-if="!examples.length" class="text-xs text-muted-foreground">{{ t('structure.types.examplesHint') }}</p>
        </div>
        <div v-if="kind === 'method'" class="space-y-1.5">
          <Label>{{ t('structure.types.weight') }}</Label>
          <Input v-model.number="weight" type="number" min="0.1" max="100" step="0.5" class="h-9 w-28" />
          <p class="text-xs text-muted-foreground">{{ t('structure.types.weightHint') }}</p>
        </div>
        <div v-if="isEdit && knowledgePoints?.length" class="space-y-1.5">
          <Label>{{ t('structure.types.knowledgePoints') }}</Label>
          <KnowledgePointSelector v-model="knowledgePointIds" :knowledge-points="knowledgePoints" />
          <p class="text-xs text-muted-foreground">{{ t('structure.types.knowledgePointsHint') }}</p>
        </div>
        <div class="space-y-1.5">
          <Label>{{ t('structure.types.status') }}</Label>
          <NativeSelect v-model="status" class="h-9 w-40">
            <NativeSelectOption v-for="option in statusOptions" :key="option.value" :value="option.value">{{ option.label }}</NativeSelectOption>
          </NativeSelect>
        </div>
      </div>

      <DialogFooter>
        <Button variant="outline" @click="isOpen = false">{{ t('common.cancel') }}</Button>
        <Button :disabled="!canSubmit" @click="submit">{{ t('common.save') }}</Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
