<script setup lang="ts">
// 答案汇总模块（question_details）编辑器：WYSIWYG 展示真实冻结题目字段，
// 提供全局 answer/thinking/analysis/summary 开关、题级 included 与三态 override，
// 并可在某题（answer_item）之前新增/编辑 heading/rich_text。answer_item 不可重排。
import { computed } from 'vue'
import RichEditor from '@/components/rich-editor/RichEditor.vue'
import RichContent from '@/components/rich-editor/RichContent.vue'
import AnswerDisplay from '@/components/AnswerDisplay.vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import {
  ArrowUp, ArrowDown, Trash2, ListChecks, Plus, Type, Heading,
  AlignLeft, AlignCenter, AlignRight, AlignJustify,
} from '@lucide/vue'
import { questionTypeLabel } from '@/lib/answerFormat'
import {
  detailPropsOf, headingAlignOf, headingClassFor, headingDocToText, headingLevelOf,
  headingTextToDoc, questionNumberOf, setHeadingAlign,
} from '@/lib/compositionDocument'
import type { EditorNode, HeadingAlign } from '@/lib/compositionDocument'
import { ANSWER_FIELD_KEYS } from '@/types/composition'
import type { AnswerFieldKey, DetailScope, HeadingLevel } from '@/types/composition'
import type { RichDoc } from '@/types'

const props = defineProps<{
  node: EditorNode
  index: number
  total: number
  // question 节点 UUID → 节点（用于解析 answer_item 的冻结题目内容）。
  questionNodeMap: Map<string, EditorNode>
  // 题号开关：开启时汇总模块内每题也显示题号。
  numberingEnabled?: boolean
  // 激活态：true 显示编辑控件；false 以渲染态（只读排版）展示。
  active?: boolean
}>()

const emit = defineEmits<{
  patch: [patch: Partial<Pick<EditorNode, 'props'>>]
  move: [direction: 'up' | 'down']
  remove: []
  activate: []
  'patch-child': [childId: string, patch: Partial<Pick<EditorNode, 'content' | 'props'>>]
  'move-child': [childId: string, direction: 'up' | 'down']
  'remove-child': [childId: string]
  'add-custom': [answerItemId: string | null, nodeType: 'heading' | 'rich_text']
}>()

const FIELD_LABELS: Record<AnswerFieldKey, string> = {
  answer: '答案',
  thinking: '思路',
  analysis: '解析',
  summary: '小结',
}

const detail = computed(() => detailPropsOf(props.node))

const scopeModel = computed<DetailScope>({
  get: () => detail.value.scope,
  set: (v) => emit('patch', { props: { ...detail.value, scope: v, fields: { ...detail.value.fields } } }),
})

function toggleGlobalField(key: AnswerFieldKey, value: boolean) {
  emit('patch', {
    props: { ...detail.value, fields: { ...detail.value.fields, [key]: value } },
  })
}

// 仅 answer_item 子节点（保留原顺序），供 WYSIWYG 渲染与 override 编辑。
const answerItems = computed(() => props.node.children.filter((c) => c.nodeType === 'answer_item'))
const hasChildren = computed(() => props.node.children.length > 0)

function sourceQuestion(child: EditorNode): EditorNode | null {
  return child.sourceQuestionNodeId ? props.questionNodeMap.get(child.sourceQuestionNodeId) ?? null : null
}

function questionNumber(child: EditorNode): string {
  const q = sourceQuestion(child)
  return q ? questionNumberOf(q) : ''
}

// 渲染态：题号只贴在首个可见字段行上（各题可见字段集合一致，取全局开关顺序中的第一个）。
const firstVisibleFieldKey = computed<AnswerFieldKey | null>(
  () => ANSWER_FIELD_KEYS.find((k) => detail.value.fields[k]) ?? null,
)

// --- 自定义子节点（heading/rich_text）编辑 ---
function childRichModel(child: EditorNode) {
  return computed<RichDoc>({
    get: () => child.content,
    set: (v) => emit('patch-child', child.id, { content: v }),
  })
}

function onChildHeadingInput(child: EditorNode, value: string) {
  emit('patch-child', child.id, { content: headingTextToDoc(value, headingAlignOf(child.content)) })
}

// heading 段落对齐（复用 RichDoc paragraph.textAlign）。
const HEADING_ALIGN_ITEMS: { value: HeadingAlign; label: string; icon: unknown }[] = [
  { value: 'left', label: '左对齐', icon: AlignLeft },
  { value: 'center', label: '居中', icon: AlignCenter },
  { value: 'right', label: '右对齐', icon: AlignRight },
  { value: 'justify', label: '两端对齐', icon: AlignJustify },
]
function childHeadingAlignIcon(child: EditorNode) {
  const align = headingAlignOf(child.content)
  return HEADING_ALIGN_ITEMS.find((i) => i.value === align)?.icon ?? AlignLeft
}
function setChildHeadingAlign(child: EditorNode, align: HeadingAlign) {
  emit('patch-child', child.id, { content: setHeadingAlign(child.content, align) })
}

function childHeadingLevel(child: EditorNode) {
  return computed<string>({
    get: () => String(headingLevelOf(child)),
    set: (v) => emit('patch-child', child.id, { props: { level: Number(v) as HeadingLevel } }),
  })
}
</script>

<template>
  <div
    data-composition-block
    class="group relative rounded-lg transition-colors"
    :class="active ? 'border-2 border-primary/30 bg-primary/5' : 'cursor-text hover:bg-muted/40'"
    @click.stop="emit('activate')"
  >
    <!-- 浮动操作条：渲染态隐藏、悬浮/激活时浮现，不占文档流 -->
    <div
      class="absolute -top-3 right-2 z-10 flex items-center gap-1 rounded-md border bg-card px-1.5 py-0.5 shadow-sm transition-opacity"
      :class="active ? 'opacity-100' : 'opacity-0 group-hover:opacity-100 focus-within:opacity-100'"
    >
      <ListChecks class="h-3.5 w-3.5 text-primary" />
      <span class="text-xs font-semibold text-primary">参考答案模块</span>
      <div class="ml-1 flex items-center gap-0.5">
        <TooltipProvider :delay-duration="300">
          <Tooltip>
            <TooltipTrigger as-child>
              <Button variant="ghost" size="icon" class="h-7 w-7" :disabled="index === 0" @click="emit('move', 'up')">
                <ArrowUp class="h-3.5 w-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>上移</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger as-child>
              <Button variant="ghost" size="icon" class="h-7 w-7" :disabled="index === total - 1" @click="emit('move', 'down')">
                <ArrowDown class="h-3.5 w-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>下移</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger as-child>
              <Button variant="ghost" size="icon" class="h-7 w-7 text-destructive hover:text-destructive" @click="emit('remove')">
                <Trash2 class="h-3.5 w-3.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>删除模块</TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>
    </div>

    <!-- 编辑态：完整模块编辑器 -->
    <template v-if="active">
      <!-- 范围选择 -->
      <div class="flex items-center gap-2 border-b border-primary/20 px-3 py-1.5">
        <span class="text-xs font-semibold text-primary">范围</span>
        <Select v-model="scopeModel">
          <SelectTrigger class="ml-1 h-7 w-40 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全篇题目</SelectItem>
            <SelectItem value="before">此模块之前的题目</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <!-- 全局字段开关 -->
      <div class="flex flex-wrap items-center gap-x-6 gap-y-2 border-b border-primary/20 px-3 py-2">
        <span class="text-xs font-medium text-muted-foreground">全局显示：</span>
        <label v-for="key in ANSWER_FIELD_KEYS" :key="key" class="flex items-center gap-1.5 text-xs">
          <Switch :model-value="detail.fields[key]" @update:model-value="toggleGlobalField(key, $event)" />
          {{ FIELD_LABELS[key] }}
        </label>
      </div>

      <!-- WYSIWYG 子节点序列 -->
      <div class="space-y-3 p-3">
        <p v-if="!hasChildren" class="rounded-md border border-dashed py-6 text-center text-xs text-muted-foreground">
          此范围内暂无题目，添加题目后将自动生成对应答案项。
        </p>

        <template v-for="child in node.children" :key="child.id">
          <!-- 自定义标题 -->
          <div v-if="child.nodeType === 'heading'" class="rounded-md border bg-card p-2">
            <div class="mb-1 flex items-center gap-2">
              <Heading class="h-3 w-3 text-muted-foreground" />
              <span class="text-[11px] text-muted-foreground">自定义标题</span>
              <Select :model-value="String(headingLevelOf(child))" @update:model-value="(v: any) => emit('patch-child', child.id, { props: { level: Number(v) as HeadingLevel } })">
                <SelectTrigger class="h-6 w-16 text-[11px]"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="1">H1</SelectItem>
                  <SelectItem value="2">H2</SelectItem>
                  <SelectItem value="3">H3</SelectItem>
                  <SelectItem value="4">H4</SelectItem>
                </SelectContent>
              </Select>
              <DropdownMenu>
                <DropdownMenuTrigger as-child>
                  <Button variant="ghost" size="icon" class="h-6 w-6" title="对齐方式">
                    <component :is="childHeadingAlignIcon(child)" class="h-3 w-3" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start">
                  <DropdownMenuItem
                    v-for="item in HEADING_ALIGN_ITEMS"
                    :key="item.value"
                    :class="headingAlignOf(child.content) === item.value ? 'bg-accent' : ''"
                    @click="setChildHeadingAlign(child, item.value)"
                  >
                    <component :is="item.icon" class="mr-2 h-4 w-4" /> {{ item.label }}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
              <div class="ml-auto flex items-center gap-0.5">
                <Button variant="ghost" size="icon" class="h-6 w-6" @click="emit('move-child', child.id, 'up')"><ArrowUp class="h-3 w-3" /></Button>
                <Button variant="ghost" size="icon" class="h-6 w-6" @click="emit('move-child', child.id, 'down')"><ArrowDown class="h-3 w-3" /></Button>
                <Button variant="ghost" size="icon" class="h-6 w-6 text-destructive" @click="emit('remove-child', child.id)"><Trash2 class="h-3 w-3" /></Button>
              </div>
            </div>
            <Input
              :model-value="headingDocToText(child.content)"
              placeholder="标题文字…"
              class="h-8 font-semibold"
              :style="{ textAlign: headingAlignOf(child.content) === 'left' ? undefined : headingAlignOf(child.content) }"
              @update:model-value="onChildHeadingInput(child, String($event))"
            />
          </div>

          <!-- 自定义文本 -->
          <div v-else-if="child.nodeType === 'rich_text'" class="rounded-md border bg-card p-2">
            <div class="mb-1 flex items-center gap-2">
              <Type class="h-3 w-3 text-muted-foreground" />
              <span class="text-[11px] text-muted-foreground">自定义文本</span>
              <div class="ml-auto flex items-center gap-0.5">
                <Button variant="ghost" size="icon" class="h-6 w-6" @click="emit('move-child', child.id, 'up')"><ArrowUp class="h-3 w-3" /></Button>
                <Button variant="ghost" size="icon" class="h-6 w-6" @click="emit('move-child', child.id, 'down')"><ArrowDown class="h-3 w-3" /></Button>
                <Button variant="ghost" size="icon" class="h-6 w-6 text-destructive" @click="emit('remove-child', child.id)"><Trash2 class="h-3 w-3" /></Button>
              </div>
            </div>
            <RichEditor :model-value="child.content" placeholder="输入文本…" @update:model-value="(v: RichDoc) => emit('patch-child', child.id, { content: v })" />
          </div>

          <!-- answer_item：WYSIWYG 真实冻结题目字段 + 题级配置（不可重排） -->
          <div v-else-if="child.nodeType === 'answer_item'" class="rounded-md border bg-card">
            <div class="flex flex-wrap items-center gap-2 border-b px-3 py-1.5">
              <Badge
                v-if="numberingEnabled"
                variant="outline"
                class="text-xs font-medium"
                :class="questionNumber(child) ? '' : 'text-muted-foreground/50'"
              >
                {{ questionNumber(child) || '__' }}
              </Badge>
              <template v-if="sourceQuestion(child)?.questionContent">
                <Badge variant="secondary" class="text-xs">{{ questionTypeLabel(sourceQuestion(child)!.questionContent!.q_type) }}</Badge>
                <span class="text-xs text-muted-foreground">#{{ sourceQuestion(child)!.questionId }}</span>
              </template>
              <span v-else class="text-xs text-destructive">题目内容不可用</span>
              <DropdownMenu>
                <DropdownMenuTrigger as-child>
                  <Button variant="ghost" size="sm" class="ml-auto h-6 gap-1 px-2 text-[11px]">
                    <Plus class="h-3 w-3" /> 在此题前插入
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem @click="emit('add-custom', child.id, 'heading')">
                    <Heading class="mr-2 h-4 w-4" /> 标题
                  </DropdownMenuItem>
                  <DropdownMenuItem @click="emit('add-custom', child.id, 'rich_text')">
                    <Type class="mr-2 h-4 w-4" /> 文本
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>

            <div class="space-y-2 p-3">
              <!-- 字段可见性由模块头部全局开关决定；可见则渲染真实冻结内容 -->
              <template v-for="key in ANSWER_FIELD_KEYS" :key="key">
                <div v-if="detail.fields[key]" class="flex items-start gap-2">
                  <span class="w-10 shrink-0 pt-0.5 text-[11px] font-medium text-muted-foreground">
                    {{ FIELD_LABELS[key] }}
                  </span>
                  <div class="min-w-0 flex-1 text-sm">
                    <template v-if="sourceQuestion(child)?.questionContent">
                      <AnswerDisplay
                        v-if="key === 'answer'"
                        :answer="sourceQuestion(child)!.questionContent!.answer"
                        :options="sourceQuestion(child)!.questionContent!.options"
                      />
                      <RichContent
                        v-else
                        :content="sourceQuestion(child)!.questionContent![key]"
                        class="[&_.prose]:my-0"
                        empty-text="（空）"
                      />
                    </template>
                  </div>
                </div>
              </template>
            </div>
          </div>
        </template>

        <div class="flex justify-center pt-1">
          <DropdownMenu>
            <DropdownMenuTrigger as-child>
              <Button variant="outline" size="sm" class="h-8 gap-1.5 text-xs">
                <Plus class="h-3.5 w-3.5" /> 添加模块内容
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="center">
              <DropdownMenuItem @click="emit('add-custom', null, 'heading')">
                <Heading class="mr-2 h-4 w-4" /> 尾部标题
              </DropdownMenuItem>
              <DropdownMenuItem @click="emit('add-custom', null, 'rich_text')">
                <Type class="mr-2 h-4 w-4" /> 尾部文本
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </template>

    <!-- 渲染态：只读排版，隐藏所有编辑控件 -->
    <div v-else class="space-y-2 px-3 py-2">
      <p v-if="!hasChildren" class="text-xs text-muted-foreground">此范围内暂无题目。</p>
      <template v-for="child in node.children" :key="child.id">
        <!-- 自定义标题 -->
        <div v-if="child.nodeType === 'heading'" :class="headingClassFor(headingLevelOf(child))">
          <RichContent :content="child.content" class="[&_.prose]:my-0" />
        </div>

        <!-- 自定义文本 -->
        <RichContent v-else-if="child.nodeType === 'rich_text'" :content="child.content" />

        <!-- answer_item：按全局字段渲染真实冻结内容；题号与首个可见字段同行，紧凑排布 -->
        <div v-else-if="child.nodeType === 'answer_item'" class="space-y-1 border-l-2 border-muted pl-2.5 text-sm">
          <template v-if="sourceQuestion(child)?.questionContent">
            <template v-for="key in ANSWER_FIELD_KEYS" :key="key">
              <div v-if="detail.fields[key]" class="flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5">
                <span v-if="key === firstVisibleFieldKey && numberingEnabled && questionNumber(child)" class="font-medium text-muted-foreground">
                  {{ questionNumber(child) }}.
                </span>
                <span class="shrink-0 text-xs font-medium text-muted-foreground">{{ FIELD_LABELS[key] }}：</span>
                <AnswerDisplay
                  v-if="key === 'answer'"
                  :answer="sourceQuestion(child)!.questionContent!.answer"
                  :options="sourceQuestion(child)!.questionContent!.options"
                />
                <RichContent v-else :content="sourceQuestion(child)!.questionContent![key]" class="[&_.prose]:my-0" empty-text="（空）" />
              </div>
            </template>
          </template>
          <span v-else class="text-xs text-destructive">题目内容不可用</span>
        </div>
      </template>
    </div>
  </div>
</template>
