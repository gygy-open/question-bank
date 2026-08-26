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
  ArrowUp, ArrowDown, Trash2, ListChecks, Plus, Type, Heading, FileQuestion,
} from '@lucide/vue'
import { questionTypeLabel } from '@/lib/answerFormat'
import {
  answerItemPropsOf, detailPropsOf, headingDocToText, headingLevelOf, headingTextToDoc,
} from '@/lib/compositionDocument'
import type { EditorNode } from '@/lib/compositionDocument'
import { ANSWER_FIELD_KEYS } from '@/types/composition'
import type { AnswerFieldKey, AnswerItemOverride, DetailScope, HeadingLevel } from '@/types/composition'
import type { RichDoc } from '@/types'

const props = defineProps<{
  node: EditorNode
  index: number
  total: number
  // question 节点 UUID → 节点（用于解析 answer_item 的冻结题目内容）。
  questionNodeMap: Map<string, EditorNode>
}>()

const emit = defineEmits<{
  patch: [patch: Partial<Pick<EditorNode, 'props'>>]
  move: [direction: 'up' | 'down']
  remove: []
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

/** 有效可见字段：included && (override ?? 全局开关)。 */
function effectiveFields(child: EditorNode): Record<AnswerFieldKey, boolean> {
  const ai = answerItemPropsOf(child)
  const out = {} as Record<AnswerFieldKey, boolean>
  for (const key of ANSWER_FIELD_KEYS) {
    const override = ai.overrides[key]
    const base = override == null ? Boolean(detail.value.fields[key]) : override
    out[key] = ai.included && base
  }
  return out
}

function includedModel(child: EditorNode): boolean {
  return answerItemPropsOf(child).included
}

function setIncluded(child: EditorNode, value: boolean) {
  const ai = answerItemPropsOf(child)
  emit('patch-child', child.id, { props: { included: value, overrides: { ...ai.overrides } } })
}

function overrideModel(child: EditorNode, key: AnswerFieldKey): 'inherit' | 'show' | 'hide' {
  const v = answerItemPropsOf(child).overrides[key]
  return v == null ? 'inherit' : v ? 'show' : 'hide'
}

function setOverride(child: EditorNode, key: AnswerFieldKey, value: string) {
  const next: AnswerItemOverride = value === 'inherit' ? null : value === 'show'
  const ai = answerItemPropsOf(child)
  emit('patch-child', child.id, {
    props: { included: ai.included, overrides: { ...ai.overrides, [key]: next } },
  })
}

// --- 自定义子节点（heading/rich_text）编辑 ---
function childRichModel(child: EditorNode) {
  return computed<RichDoc>({
    get: () => child.content,
    set: (v) => emit('patch-child', child.id, { content: v }),
  })
}

function onChildHeadingInput(child: EditorNode, value: string) {
  emit('patch-child', child.id, { content: headingTextToDoc(value) })
}

function childHeadingLevel(child: EditorNode) {
  return computed<string>({
    get: () => String(headingLevelOf(child)),
    set: (v) => emit('patch-child', child.id, { props: { level: Number(v) as HeadingLevel } }),
  })
}
</script>

<template>
  <div class="rounded-lg border-2 border-primary/30 bg-primary/5">
    <!-- 模块头 -->
    <div class="flex items-center gap-2 border-b border-primary/20 px-3 py-1.5">
      <ListChecks class="h-3.5 w-3.5 text-primary" />
      <span class="text-xs font-semibold text-primary">答案汇总模块</span>
      <Select v-model="scopeModel">
        <SelectTrigger class="ml-1 h-7 w-40 text-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">全篇题目</SelectItem>
          <SelectItem value="before">此模块之前的题目</SelectItem>
        </SelectContent>
      </Select>
      <div class="ml-auto flex items-center gap-0.5">
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
            <FileQuestion class="h-3.5 w-3.5 text-muted-foreground" />
            <template v-if="sourceQuestion(child)?.questionContent">
              <Badge variant="secondary" class="text-xs">{{ questionTypeLabel(sourceQuestion(child)!.questionContent!.q_type) }}</Badge>
              <span class="text-xs text-muted-foreground">#{{ sourceQuestion(child)!.questionId }}</span>
            </template>
            <span v-else class="text-xs text-destructive">题目内容不可用</span>
            <label class="ml-auto flex items-center gap-1.5 text-xs">
              <Switch :model-value="includedModel(child)" @update:model-value="setIncluded(child, $event)" />
              包含此题
            </label>
            <DropdownMenu>
              <DropdownMenuTrigger as-child>
                <Button variant="ghost" size="sm" class="h-6 gap-1 px-2 text-[11px]">
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
            <!-- 题干（始终显示，便于对位） -->
            <RichContent
              v-if="sourceQuestion(child)?.questionContent"
              :content="sourceQuestion(child)!.questionContent!.content"
              class="text-sm text-muted-foreground [&_.prose]:my-0"
              empty-text="（无题干）"
            />

            <!-- 每字段：三态 override + 有效可见时渲染真实冻结内容 -->
            <div v-for="key in ANSWER_FIELD_KEYS" :key="key" class="flex items-start gap-2">
              <Select
                :model-value="overrideModel(child, key)"
                @update:model-value="(v: any) => setOverride(child, key, String(v))"
              >
                <SelectTrigger class="h-7 w-28 shrink-0 text-[11px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="inherit">{{ FIELD_LABELS[key] }}·继承</SelectItem>
                  <SelectItem value="show">{{ FIELD_LABELS[key] }}·显示</SelectItem>
                  <SelectItem value="hide">{{ FIELD_LABELS[key] }}·隐藏</SelectItem>
                </SelectContent>
              </Select>
              <div class="min-w-0 flex-1 pt-0.5 text-sm">
                <template v-if="effectiveFields(child)[key] && sourceQuestion(child)?.questionContent">
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
                <span v-else class="text-xs text-muted-foreground/60">（不显示）</span>
              </div>
            </div>
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
  </div>
</template>
