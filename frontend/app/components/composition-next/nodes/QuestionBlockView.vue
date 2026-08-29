<script setup lang="ts">
// 题目块 NodeView：只读渲染冻结快照（题干/选项/答案字段），并提供题号/分值/选项排版/字段显隐编辑。
import { computed, inject, ref, nextTick } from 'vue'
import { NodeViewWrapper } from '@tiptap/vue-3'
import RichContent from '@/components/rich-editor/RichContent.vue'
import AnswerDisplay from '@/components/AnswerDisplay.vue'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Trash2, Eye, ScanEye, AlertTriangle, RefreshCw } from '@lucide/vue'
import { questionTypeLabel } from '@/lib/answerFormat'
import {
  effectiveQuestionField, questionNodeStatus, questionNumberOf, questionOptionLayoutOf,
  questionPropsWithNumber, questionPropsWithOptionLayout, questionPropsWithScore,
  questionPropsWithShow, questionScoreOf, questionShowOverride, resolveOptionColumns,
} from '@/lib/compositionDocument'
import type { EditorNode } from '@/lib/compositionDocument'
import { ANSWER_FIELD_KEYS } from '@/types/composition'
import type { AnswerFieldKey, OptionLayout, QuestionContentSnapshot, QuestionProps } from '@/types/composition'
import {
  DISPLAY_FIELDS_KEY, FALLBACK_DISPLAY, FALLBACK_NUMBERING, FALLBACK_SCORING, FALLBACK_STATUS,
  FALLBACK_SYNC_DISABLED, NUMBERING_ENABLED_KEY, QUESTION_STATUS_KEY, SCORING_ENABLED_KEY,
  SYNC_DISABLED_KEY, SYNC_QUESTIONS_KEY, noopSync,
} from '../editorContext'

const props = defineProps<{
  node: { attrs: Record<string, unknown> }
  updateAttributes: (attrs: Record<string, unknown>) => void
  deleteNode: () => void
  selected?: boolean
}>()

const numberingEnabled = inject(NUMBERING_ENABLED_KEY, FALLBACK_NUMBERING)
const scoringEnabled = inject(SCORING_ENABLED_KEY, FALLBACK_SCORING)
const displayFields = inject(DISPLAY_FIELDS_KEY, FALLBACK_DISPLAY)
const questionStatusMap = inject(QUESTION_STATUS_KEY, FALLBACK_STATUS)
const syncQuestions = inject(SYNC_QUESTIONS_KEY, noopSync)
const syncDisabled = inject(SYNC_DISABLED_KEY, FALLBACK_SYNC_DISABLED)

const nodeStatus = computed(() => {
  const qid = props.node.attrs.questionId as number | null
  const st = qid != null ? questionStatusMap.value.get(qid) : null
  return questionNodeStatus(
    { nodeType: 'question', questionId: qid, questionRevision: props.node.attrs.questionRevision } as EditorNode,
    st,
  )
})
const isStale = computed(() => nodeStatus.value.stale)
const isDeleted = computed(() => nodeStatus.value.deleted)
function syncThis() {
  if (!syncDisabled.value) syncQuestions([props.node.attrs.uid as string])
}

const snapshot = computed<QuestionContentSnapshot | null>(() => (props.node.attrs.snapshot as QuestionContentSnapshot | null) ?? null)
const qProps = computed<QuestionProps | null>(() => (props.node.attrs.props as QuestionProps | null) ?? null)
// helper 只读 node.props，用轻量 shim 复用 compositionDocument 的 props 访问/合并逻辑。
const shim = computed(() => ({ props: qProps.value }) as unknown as EditorNode)

const typeLabel = computed(() => (snapshot.value ? questionTypeLabel(snapshot.value.q_type) : '题目'))

function setProps(next: QuestionProps) {
  props.updateAttributes({ props: Object.keys(next).length ? next : null })
}

const questionNumber = computed<string>({
  get: () => questionNumberOf(shim.value),
  set: (v) => setProps(questionPropsWithNumber(shim.value, v)),
})
const questionScore = computed<number | null>({
  get: () => questionScoreOf(shim.value),
  set: (v) => setProps(questionPropsWithScore(shim.value, v)),
})

const OPTION_LAYOUT_ITEMS: { value: OptionLayout; label: string }[] = [
  { value: 'auto', label: '自动' },
  { value: 1, label: '1 列' },
  { value: 2, label: '2 列' },
  { value: 4, label: '4 列' },
]
const optionLayout = computed<string>({
  get: () => String(questionOptionLayoutOf(shim.value)),
  set: (v) => {
    const layout = (v === '1' || v === '2' || v === '4' ? Number(v) : 'auto') as OptionLayout
    setProps(questionPropsWithOptionLayout(shim.value, layout))
  },
})
const optionColumns = computed(() => resolveOptionColumns(snapshot.value?.options, questionOptionLayoutOf(shim.value)))

const FIELD_LABELS: Record<AnswerFieldKey, string> = { answer: '答案', thinking: '思路', analysis: '解析', summary: '小结' }
const previewAll = ref(false)

function fieldVisible(key: AnswerFieldKey): boolean {
  if (previewAll.value) return true
  return effectiveQuestionField(shim.value, displayFields.value, key)
}
function showModel(key: AnswerFieldKey): 'inherit' | 'show' | 'hide' {
  const v = questionShowOverride(shim.value, key)
  return v == null ? 'inherit' : v ? 'show' : 'hide'
}
function setShow(key: AnswerFieldKey, value: string) {
  const next = value === 'inherit' ? null : value === 'show'
  props.updateAttributes({ props: questionPropsWithShow(shim.value, key, next) })
}

// 题号静息态显示为文本，点击才换成原生 input 并对焦（避开 shadcn Input 组件无法对外暴露 focus）。
const editingNumber = ref(false)
const numberInputRef = ref<HTMLInputElement | null>(null)
function startEditNumber() {
  editingNumber.value = true
  nextTick(() => numberInputRef.value?.focus())
}
function stopEditNumber() {
  editingNumber.value = false
}
const numberDisplay = computed(() => (questionNumber.value ? `${questionNumber.value}.` : '#'))

// 分值同样静息态显示为文本（始终用（）包裹），点击才切换为可编辑输入框。
const editingScore = ref(false)
const scoreInputRef = ref<HTMLInputElement | null>(null)
function startEditScore() {
  editingScore.value = true
  nextTick(() => scoreInputRef.value?.focus())
}
function stopEditScore() {
  editingScore.value = false
}
const scoreDisplay = computed(() => `（${questionScore.value != null ? `${questionScore.value}分` : '分值'}）`)
</script>

<template>
  <NodeViewWrapper
    data-composition-block
    class="group relative -mx-3 my-2 rounded-lg border border-transparent px-3 py-3 transition-colors hover:border-border hover:bg-card/50 focus-within:border-border focus-within:bg-card/50"
    :class="selected ? 'border-border bg-card' : ''"
    contenteditable="false"
  >
    <!-- 浮动控制条：悬浮/选中时浮现 -->
    <div
      class="absolute -top-3 right-2 z-10 flex items-center gap-1 rounded-md border bg-card px-1.5 py-0.5 shadow-sm transition-opacity"
      :class="selected ? 'opacity-100' : 'opacity-0 group-hover:opacity-100 focus-within:opacity-100'"
    >
      <Badge variant="secondary" class="text-[11px]">{{ typeLabel }}</Badge>
      <span class="text-[11px] text-muted-foreground">#{{ node.attrs.questionId }} · r{{ node.attrs.questionRevision }}</span>
      <Badge v-if="isStale" variant="outline" class="gap-1 border-amber-400 text-[11px] text-amber-600 dark:text-amber-400">
        <AlertTriangle class="h-3 w-3" /> 题库有更新
      </Badge>
      <Badge v-else-if="isDeleted" variant="outline" class="gap-1 border-destructive text-[11px] text-destructive">
        <AlertTriangle class="h-3 w-3" /> 题库已删除
      </Badge>
      <Button
        v-if="isStale" variant="ghost" size="sm" class="h-6 gap-1 px-2 text-[11px]"
        :disabled="syncDisabled" title="把此题更新为题库最新内容"
        @click="syncThis"
      >
        <RefreshCw class="h-3 w-3" /> 同步此题
      </Button>
      <Select v-if="snapshot?.options?.length" v-model="optionLayout">
        <SelectTrigger class="h-6 w-20 text-[11px]"><SelectValue /></SelectTrigger>
        <SelectContent>
          <SelectItem v-for="it in OPTION_LAYOUT_ITEMS" :key="String(it.value)" :value="String(it.value)">选项 {{ it.label }}</SelectItem>
        </SelectContent>
      </Select>
      <Popover>
        <PopoverTrigger as-child>
          <Button variant="ghost" size="sm" class="h-6 gap-1 px-2 text-[11px]"><Eye class="h-3 w-3" /> 显示</Button>
        </PopoverTrigger>
        <PopoverContent align="end" class="w-52 space-y-2" data-rich-overlay>
          <p class="text-xs font-medium text-muted-foreground">此题字段显示</p>
          <div v-for="key in ANSWER_FIELD_KEYS" :key="key" class="flex items-center justify-between gap-2">
            <span class="text-xs">{{ FIELD_LABELS[key] }}</span>
            <Select :model-value="showModel(key)" @update:model-value="(v: any) => setShow(key, String(v))">
              <SelectTrigger class="h-7 w-24 text-[11px]"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="inherit">继承</SelectItem>
                <SelectItem value="show">显示</SelectItem>
                <SelectItem value="hide">隐藏</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </PopoverContent>
      </Popover>
      <Button
        variant="ghost" size="icon" class="h-7 w-7"
        :class="previewAll ? 'text-primary' : ''"
        title="临时预览全部内容"
        @click="previewAll = !previewAll"
      >
        <ScanEye class="h-3.5 w-3.5" />
      </Button>
      <Button variant="ghost" size="icon" class="h-7 w-7 text-destructive hover:text-destructive" title="删除" @click="deleteNode()">
        <Trash2 class="h-3.5 w-3.5" />
      </Button>
    </div>

    <div v-if="!snapshot" class="flex items-center gap-2 py-2 text-sm text-destructive">
      <AlertTriangle class="h-4 w-4" /> 题目内容不可用（#{{ node.attrs.questionId }}）
    </div>
    <div v-else class="space-y-3">
      <div class="flex items-baseline gap-2 text-sm">
        <template v-if="numberingEnabled">
          <!-- 静息态显示纯文本；点击才切换为可编辑输入框，无需先选中整块即可编辑 -->
          <span class="inline-flex shrink-0 items-baseline">
            <input
              v-if="editingNumber"
              ref="numberInputRef"
              :value="questionNumber"
              placeholder="#"
              class="h-6 w-10 rounded border border-input bg-background px-1 text-sm font-medium shadow-xs outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-3"
              @input="questionNumber = ($event.target as HTMLInputElement).value"
              @blur="stopEditNumber"
              @keydown.enter.prevent="stopEditNumber"
              @keydown.escape.prevent="stopEditNumber"
            >
            <button
              v-else
              type="button"
              class="appearance-none rounded bg-transparent px-1 align-baseline font-medium leading-5 hover:bg-accent"
              :class="questionNumber ? '' : 'text-muted-foreground'"
              @click="startEditNumber"
            >{{ numberDisplay }}</button>
          </span>
        </template>
        <div class="min-w-0 flex-1 space-y-2">
          <div class="flow-root">
            <template v-if="scoringEnabled">
              <!-- 浮动的归并词需与题干段落同行高，否则两者的盒顶不在同一行高内会看起来错位 -->
              <span class="float-left inline-flex items-baseline font-medium leading-5 text-muted-foreground">
                <template v-if="editingScore">（<input
                  ref="scoreInputRef"
                  type="number" min="0" max="1000" step="0.5"
                  :value="questionScore ?? ''"
                  placeholder="分值"
                  class="no-spinner h-6 w-14 rounded border border-input bg-background text-center text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-3"
                  @input="questionScore = ($event.target as HTMLInputElement).value === '' ? null : Number(($event.target as HTMLInputElement).value)"
                  @blur="stopEditScore"
                  @keydown.enter.prevent="stopEditScore"
                  @keydown.escape.prevent="stopEditScore"
                >分）</template>
                <button
                  v-else
                  type="button"
                  class="appearance-none rounded bg-transparent align-baseline leading-5 hover:bg-accent"
                  @click="startEditScore"
                >{{ scoreDisplay }}</button>
              </span>
            </template>
            <RichContent :content="snapshot.content" empty-text="（无题干）" class="[&_p]:my-0 [&_p]:!leading-5" />
          </div>
          <ul
            v-if="snapshot.options?.length"
            class="grid gap-x-6 gap-y-1"
            :style="{ gridTemplateColumns: `repeat(${optionColumns}, minmax(0, 1fr))` }"
          >
            <li v-for="opt in snapshot.options" :key="opt.id" class="flex items-baseline gap-2 text-sm">
              <span class="font-medium text-muted-foreground">{{ opt.label }}.</span>
              <RichContent :content="opt.content" class="min-w-0 [&_p]:my-0" />
            </li>
          </ul>
        </div>
      </div>
      <template v-for="key in ANSWER_FIELD_KEYS" :key="key">
        <div v-if="fieldVisible(key)" class="rounded-md bg-muted/50 px-3 py-2">
          <p class="mb-1 text-xs font-medium text-muted-foreground">{{ FIELD_LABELS[key] }}</p>
          <AnswerDisplay v-if="key === 'answer'" :answer="snapshot.answer" :options="snapshot.options" />
          <RichContent v-else :content="snapshot[key]" class="[&_.prose]:my-0" empty-text="（空）" />
        </div>
      </template>
    </div>
  </NodeViewWrapper>
</template>

<style scoped>
/* 去掉分值输入框右侧的数字进步器（上下箭头） */
.no-spinner::-webkit-outer-spin-button,
.no-spinner::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}
.no-spinner {
  appearance: textfield;
  -moz-appearance: textfield;
}
</style>

