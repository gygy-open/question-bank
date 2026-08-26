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
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import {
  ArrowUp, ArrowDown, Trash2, Type, Heading, FileQuestion, SeparatorHorizontal,
  AlertTriangle, Pencil, RefreshCw,
} from '@lucide/vue'
import { questionTypeLabel } from '@/lib/answerFormat'
import {
  headingDocToText, headingHasRichInline, headingLevelOf, headingTextToDoc,
} from '@/lib/compositionDocument'
import type { EditorNode } from '@/lib/compositionDocument'
import type { HeadingLevel } from '@/types/composition'
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
}>()

const emit = defineEmits<{
  patch: [patch: Partial<Pick<EditorNode, 'content' | 'props'>>]
  move: [direction: 'up' | 'down']
  remove: []
  sync: []
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
  emit('patch', { content: headingTextToDoc(value) })
}

function convertHeadingToPlain() {
  forcePlainEdit.value = true
  headingText.value = headingDocToText(props.node.content)
  emit('patch', { content: headingTextToDoc(headingText.value) })
}

const headingLevel = computed<string>({
  get: () => String(headingLevelOf(props.node)),
  set: (v) => emit('patch', { props: { level: Number(v) as HeadingLevel } }),
})
</script>

<template>
  <div class="group relative rounded-lg border bg-card">
    <!-- 块头：类型标签 + 线性操作工具栏 -->
    <div class="flex items-center gap-2 border-b px-3 py-1.5">
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
      <div class="ml-auto flex items-center gap-0.5 opacity-60 transition-opacity group-hover:opacity-100">
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
    <div class="p-3">
      <!-- 文本：复用富文本编辑器 -->
      <RichEditor v-if="node.nodeType === 'rich_text'" v-model="richModel" placeholder="输入正文内容…" />

      <!-- 标题：受限单行文本 → 单段落 RichDoc；含公式时先只读，避免损坏 -->
      <template v-else-if="node.nodeType === 'heading'">
        <div class="flex items-center gap-2">
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
        </div>
      </template>

      <!-- 题目：只读渲染冻结快照（node.questionContent），绝不查询实时题库 -->
      <template v-else-if="node.nodeType === 'question'">
        <div v-if="!node.questionContent" class="flex items-center gap-2 py-4 text-sm text-destructive">
          <AlertTriangle class="h-4 w-4" /> 题目内容不可用（#{{ node.questionId }}）
        </div>
        <div v-else class="space-y-3">
          <div class="flex items-center gap-2">
            <Badge variant="secondary" class="text-xs">{{ questionTypeLabel(node.questionContent.q_type) }}</Badge>
            <span class="text-xs text-muted-foreground">#{{ node.questionId }} · 版本 r{{ node.questionRevision }}</span>
          </div>
          <RichContent :content="node.questionContent.content" empty-text="（无题干）" />
          <ul v-if="node.questionContent.options?.length" class="space-y-1">
            <li v-for="opt in node.questionContent.options" :key="opt.id" class="flex gap-2 text-sm">
              <span class="font-medium text-muted-foreground">{{ opt.label }}.</span>
              <RichContent :content="opt.content" class="[&_.prose]:my-0" />
            </li>
          </ul>
          <div class="rounded-md bg-muted/50 px-3 py-2">
            <p class="mb-1 text-xs font-medium text-muted-foreground">答案</p>
            <AnswerDisplay :answer="node.questionContent.answer" :options="node.questionContent.options" />
          </div>
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
