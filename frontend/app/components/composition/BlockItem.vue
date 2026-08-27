<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import RichEditor from '@/components/rich-editor/RichEditor.vue'
import RichContent from '@/components/rich-editor/RichContent.vue'
import AnswerDisplay from '@/components/AnswerDisplay.vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import {
  ArrowUp, ArrowDown, Trash2, Type, Heading, FileQuestion, SeparatorHorizontal,
  AlertTriangle, Pencil, RefreshCw, Eye, AlignLeft, AlignCenter, AlignRight, AlignJustify,
} from '@lucide/vue'
import { questionTypeLabel } from '@/lib/answerFormat'
import {
  effectiveQuestionField, headingAlignOf, headingClassFor, headingDocToText, headingHasRichInline,
  headingLevelOf, headingTextToDoc, questionNumberOf, questionOptionLayoutOf,
  questionPropsWithNumber, questionPropsWithOptionLayout, questionPropsWithScore, questionPropsWithShow,
  questionScoreOf, questionShowOverride, resolveOptionColumns, setHeadingAlign,
} from '@/lib/compositionDocument'
import type { EditorNode, HeadingAlign } from '@/lib/compositionDocument'
import { ANSWER_FIELD_KEYS } from '@/types/composition'
import type { AnswerFieldKey, HeadingLevel, OptionLayout } from '@/types/composition'
import type { RichDoc } from '@/types'

const props = defineProps<{
  node: EditorNode
  index: number
  total: number
  // 相对实时题库的状态：stale（题库有更新）/ deleted（题库已删除）。
  stale?: boolean
  deleted?: boolean
  // 有未保存修改或节点尚未持久化时禁止同步。
  syncDisabled?: boolean
  // 题号开关：开启时 question 块展示可编辑题号。
  numberingEnabled?: boolean
  // 赋分开关：开启时 question 块展示可编辑分值。
  scoringEnabled?: boolean
  // 全局题目显示字段（answer/thinking/analysis/summary）。
  globalDisplayFields?: Record<AnswerFieldKey, boolean>
  // 激活态：true 显示编辑控件；false 以渲染态（只读排版）展示。
  active?: boolean
}>()

const emit = defineEmits<{
  patch: [patch: Partial<Pick<EditorNode, 'content' | 'props'>>]
  move: [direction: 'up' | 'down']
  remove: []
  sync: []
  activate: []
}>()

const BLOCK_META: Record<string, { label: string; icon: unknown }> = {
  rich_text: { label: '文本', icon: Type },
  heading: { label: '标题', icon: Heading },
  question: { label: '题目', icon: FileQuestion },
  page_break: { label: '分页', icon: SeparatorHorizontal },
}

const meta = computed(() => BLOCK_META[props.node.nodeType] ?? BLOCK_META.rich_text!)

// --- rich_text ---
const richModel = computed<RichDoc>({
  get: () => props.node.content,
  set: (v) => emit('patch', { content: v }),
})

// --- heading ---
const headingText = ref(headingDocToText(props.node.content))
const forcePlainEdit = ref(false)
watch(
  () => props.node.id,
  () => {
    headingText.value = headingDocToText(props.node.content)
    forcePlainEdit.value = false
  },
)
const headingHasRich = computed(() => headingHasRichInline(props.node.content))

function onHeadingInput(value: string) {
  headingText.value = value
  emit('patch', { content: headingTextToDoc(value, headingAlignOf(props.node.content)) })
}

function convertHeadingToPlain() {
  forcePlainEdit.value = true
  headingText.value = headingDocToText(props.node.content)
  emit('patch', { content: headingTextToDoc(headingText.value, headingAlignOf(props.node.content)) })
}

// heading 段落对齐（复用 RichDoc paragraph.textAlign，无需后端改动）。
const HEADING_ALIGN_ITEMS: { value: HeadingAlign; label: string; icon: unknown }[] = [
  { value: 'left', label: '左对齐', icon: AlignLeft },
  { value: 'center', label: '居中', icon: AlignCenter },
  { value: 'right', label: '右对齐', icon: AlignRight },
  { value: 'justify', label: '两端对齐', icon: AlignJustify },
]
const headingAlign = computed(() => headingAlignOf(props.node.content))
const headingAlignIcon = computed(
  () => HEADING_ALIGN_ITEMS.find((i) => i.value === headingAlign.value)?.icon ?? AlignLeft,
)
function setHeadingAlignment(align: HeadingAlign) {
  emit('patch', { content: setHeadingAlign(props.node.content, align) })
}

const headingLevel = computed<string>({
  get: () => String(headingLevelOf(props.node)),
  set: (v) => emit('patch', { props: { level: Number(v) as HeadingLevel } }),
})

// --- question 题号 ---
const questionNumber = computed<string>({
  get: () => questionNumberOf(props.node),
  set: (v) => {
    const next = questionPropsWithNumber(props.node, v)
    emit('patch', { props: Object.keys(next).length ? next : null })
  },
})

// --- question 分值 ---
const questionScore = computed<number | null>({
  get: () => questionScoreOf(props.node),
  set: (v) => {
    const next = questionPropsWithScore(props.node, v)
    emit('patch', { props: Object.keys(next).length ? next : null })
  },
})

// --- question 选项排版（每卷覆盖） ---
const OPTION_LAYOUT_ITEMS: { value: OptionLayout; label: string }[] = [
  { value: 'auto', label: '自动' },
  { value: 1, label: '1 列' },
  { value: 2, label: '2 列' },
  { value: 4, label: '4 列' },
]
const optionLayout = computed<string>({
  get: () => String(questionOptionLayoutOf(props.node)),
  set: (v) => {
    const layout = (v === '1' || v === '2' || v === '4' ? Number(v) : 'auto') as OptionLayout
    const next = questionPropsWithOptionLayout(props.node, layout)
    emit('patch', { props: Object.keys(next).length ? next : null })
  },
})
const optionColumns = computed(() =>
  resolveOptionColumns(props.node.questionContent?.options, questionOptionLayoutOf(props.node)),
)

// --- question 字段显隐（全局 + 题目级三态覆盖） ---
const FIELD_LABELS: Record<AnswerFieldKey, string> = {
  answer: '答案', thinking: '思路', analysis: '解析', summary: '小结',
}
const DEFAULT_DISPLAY: Record<AnswerFieldKey, boolean> = {
  answer: false, thinking: false, analysis: false, summary: false,
}

function fieldVisible(key: AnswerFieldKey): boolean {
  return effectiveQuestionField(props.node, props.globalDisplayFields ?? DEFAULT_DISPLAY, key)
}

function showModel(key: AnswerFieldKey): 'inherit' | 'show' | 'hide' {
  const v = questionShowOverride(props.node, key)
  return v == null ? 'inherit' : v ? 'show' : 'hide'
}

function setShow(key: AnswerFieldKey, value: string) {
  const next = value === 'inherit' ? null : value === 'show'
  emit('patch', { props: questionPropsWithShow(props.node, key, next) })
}
</script>

<template>
  <div
    data-composition-block
    class="group relative rounded-lg transition-colors"
    :class="active ? 'border bg-card shadow-sm ring-1 ring-primary/20' : 'cursor-text hover:bg-muted/40'"
    @click.stop="emit('activate')"
  >
    <!-- 浮动操作条：渲染态隐藏、悬浮/激活/告警时浮现，不占文档流 -->
    <div
      class="absolute -top-3 right-2 z-10 flex items-center gap-1 rounded-md border bg-card px-1.5 py-0.5 shadow-sm transition-opacity"
      :class="active || stale || deleted ? 'opacity-100' : 'opacity-0 group-hover:opacity-100 focus-within:opacity-100'"
    >
      <component :is="meta.icon" class="h-3.5 w-3.5 text-muted-foreground" />
      <span class="text-xs font-medium text-muted-foreground">{{ meta.label }}</span>
      <Badge
        v-if="node.nodeType === 'question' && stale"
        variant="outline"
        class="gap-1 border-amber-400 text-amber-600 dark:text-amber-400"
      >
        <AlertTriangle class="h-3 w-3" />
        题库有更新
      </Badge>
      <Badge
        v-else-if="node.nodeType === 'question' && deleted"
        variant="outline"
        class="gap-1 border-destructive text-destructive"
      >
        <AlertTriangle class="h-3 w-3" />
        题库已删除
      </Badge>
      <TooltipProvider v-if="node.nodeType === 'question' && stale" :delay-duration="300">
        <Tooltip>
          <TooltipTrigger as-child>
            <span>
              <Button
                variant="ghost" size="sm" class="h-6 gap-1 px-2 text-xs"
                :disabled="syncDisabled"
                @click="emit('sync')"
              >
                <RefreshCw class="h-3 w-3" /> 同步此题
              </Button>
            </span>
          </TooltipTrigger>
          <TooltipContent>
            {{ syncDisabled ? '请先保存未保存的修改' : '把此题更新为题库最新内容' }}
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
      <div class="ml-1 flex items-center gap-0.5">
        <TooltipProvider :delay-duration="300">
          <Tooltip>
            <TooltipTrigger as-child>
              <Button
                variant="ghost" size="icon" class="h-7 w-7"
                :disabled="index === 0"
                @click="emit('move', 'up')"
              >
                <ArrowUp class="h-3.5 w-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>上移</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger as-child>
              <Button
                variant="ghost" size="icon" class="h-7 w-7"
                :disabled="index === total - 1"
                @click="emit('move', 'down')"
              >
                <ArrowDown class="h-3.5 w-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>下移</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger as-child>
              <Button
                variant="ghost" size="icon"
                class="h-7 w-7 text-destructive hover:text-destructive"
                @click="emit('remove')"
              >
                <Trash2 class="h-3.5 w-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>删除</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>
    </div>

    <!-- 块体 -->
    <div :class="active ? 'p-3' : 'px-3 py-2'">
      <!-- 文本：编辑态富文本编辑器 / 渲染态只读排版 -->
      <template v-if="node.nodeType === 'rich_text'">
        <RichEditor v-if="active" v-model="richModel" placeholder="输入正文内容…" />
        <RichContent v-else :content="node.content" empty-text="空文本，点击编辑…" />
      </template>

      <!-- 标题：编辑态受限单行 / 渲染态按层级排版 -->
      <template v-else-if="node.nodeType === 'heading'">
        <div v-if="active" class="flex items-center gap-2">
          <Select v-model="headingLevel">
            <SelectTrigger class="h-9 w-24 shrink-0">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="1">H1</SelectItem>
              <SelectItem value="2">H2</SelectItem>
              <SelectItem value="3">H3</SelectItem>
              <SelectItem value="4">H4</SelectItem>
            </SelectContent>
          </Select>
          <Input
            v-if="!headingHasRich || forcePlainEdit"
            :model-value="headingText"
            placeholder="标题文字…"
            class="flex-1 font-semibold"
            :style="{ textAlign: headingAlign === 'left' ? undefined : headingAlign }"
            @update:model-value="onHeadingInput(String($event))"
          />
          <div v-else class="flex flex-1 items-center gap-2">
            <RichContent :content="node.content" class="flex-1 font-semibold [&_.prose]:my-0" />
            <TooltipProvider :delay-duration="300">
              <Tooltip>
                <TooltipTrigger as-child>
                  <Button variant="ghost" size="icon" class="h-8 w-8" @click="convertHeadingToPlain">
                    <Pencil class="h-3.5 w-3.5" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>转为纯文本编辑（将丢失公式等富内容）</TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger as-child>
              <Button type="button" variant="ghost" size="icon" class="h-9 w-9 shrink-0" title="对齐方式">
                <component :is="headingAlignIcon" class="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem
                v-for="item in HEADING_ALIGN_ITEMS"
                :key="item.value"
                :class="item.value === headingAlign ? 'bg-accent' : ''"
                @click="setHeadingAlignment(item.value)"
              >
                <component :is="item.icon" class="mr-2 h-4 w-4" /> {{ item.label }}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        <div v-else :class="headingClassFor(headingLevelOf(node))">
          <RichContent :content="node.content" empty-text="空标题，点击编辑…" class="[&_.prose]:my-0" />
        </div>
      </template>

      <!-- 题目：只读渲染冻结快照（node.questionContent），编辑态额外显示题号/字段控件 -->
      <template v-else-if="node.nodeType === 'question'">
        <div v-if="!node.questionContent" class="flex items-center gap-2 py-4 text-sm text-destructive">
          <AlertTriangle class="h-4 w-4" /> 题目内容不可用（#{{ node.questionId }}）
        </div>
        <div v-else class="space-y-3">
          <div v-if="active" class="flex items-center gap-2">
            <Input
              v-if="numberingEnabled"
              :model-value="questionNumber"
              placeholder="题号"
              class="h-6 w-16 text-xs"
              @update:model-value="questionNumber = String($event)"
            />
            <Input
              v-if="scoringEnabled"
              type="number" min="0" max="1000" step="0.5"
              :model-value="questionScore ?? ''"
              placeholder="分值"
              class="h-6 w-16 text-xs"
              @update:model-value="questionScore = $event === '' ? null : Number($event)"
            />
            <Badge variant="secondary" class="text-xs">{{ questionTypeLabel(node.questionContent.q_type) }}</Badge>
            <span class="text-xs text-muted-foreground">#{{ node.questionId }} · 版本 r{{ node.questionRevision }}</span>
            <div class="ml-auto flex items-center gap-2">
              <Select v-if="node.questionContent.options?.length" v-model="optionLayout">
                <SelectTrigger class="h-6 w-24 text-[11px]"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem v-for="it in OPTION_LAYOUT_ITEMS" :key="String(it.value)" :value="String(it.value)">
                    选项 {{ it.label }}
                  </SelectItem>
                </SelectContent>
              </Select>
              <Popover>
                <PopoverTrigger as-child>
                  <Button variant="ghost" size="sm" class="h-6 gap-1 px-2 text-[11px]">
                    <Eye class="h-3 w-3" /> 显示
                  </Button>
                </PopoverTrigger>
                <PopoverContent align="end" class="w-52 space-y-2">
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
            </div>
          </div>
          <div class="flex gap-2">
            <span
              v-if="numberingEnabled && questionNumber"
              class="shrink-0 font-medium text-muted-foreground"
            >{{ questionNumber }}.</span>
            <RichContent :content="node.questionContent.content" empty-text="（无题干）" class="min-w-0 flex-1 [&_p]:my-0" />
            <span
              v-if="scoringEnabled && questionScore != null"
              class="shrink-0 text-sm text-muted-foreground"
            >（{{ questionScore }} 分）</span>
          </div>
          <ul
            v-if="node.questionContent.options?.length"
            class="grid gap-x-6 gap-y-1"
            :style="{ gridTemplateColumns: `repeat(${optionColumns}, minmax(0, 1fr))` }"
          >
            <li v-for="opt in node.questionContent.options" :key="opt.id" class="flex items-baseline gap-2 text-sm">
              <span class="font-medium text-muted-foreground">{{ opt.label }}.</span>
              <RichContent :content="opt.content" class="min-w-0 [&_p]:my-0" />
            </li>
          </ul>
          <template v-for="key in ANSWER_FIELD_KEYS" :key="key">
            <div v-if="fieldVisible(key)" class="rounded-md bg-muted/50 px-3 py-2">
              <p class="mb-1 text-xs font-medium text-muted-foreground">{{ FIELD_LABELS[key] }}</p>
              <AnswerDisplay
                v-if="key === 'answer'"
                :answer="node.questionContent.answer"
                :options="node.questionContent.options"
              />
              <RichContent
                v-else
                :content="node.questionContent[key]"
                class="[&_.prose]:my-0"
                empty-text="（空）"
              />
            </div>
          </template>
        </div>
      </template>

      <!-- 分页 -->
      <div v-else-if="node.nodeType === 'page_break'" class="flex items-center gap-3 py-1">
        <div class="h-px flex-1 border-t-2 border-dashed border-muted-foreground/40" />
        <span class="text-xs font-medium text-muted-foreground">分页</span>
        <div class="h-px flex-1 border-t-2 border-dashed border-muted-foreground/40" />
      </div>
    </div>
  </div>
</template>
