<script setup lang="ts">
// question_details 模块 NodeView（A-slim）：只读「答案联动展示块」。
// 头部 chrome 编辑 props(scope/fields)；答案按 scope + 自身文档位置从有序根节点实时派生，无可编辑内容。
import { computed, inject } from 'vue'
import { NodeViewWrapper } from '@tiptap/vue-3'
import RichContent from '@/components/rich-editor/RichContent.vue'
import AnswerDisplay from '@/components/AnswerDisplay.vue'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { AlertTriangle, Eye, ListChecks, Trash2 } from '@lucide/vue'
import { detailPropsOf, questionNumberOf } from '@/lib/compositionDocument'
import type { EditorNode } from '@/lib/compositionDocument'
import { ANSWER_FIELD_KEYS } from '@/types/composition'
import type { AnswerFieldKey, DetailScope } from '@/types/composition'
import {
  FALLBACK_NUMBERING, FALLBACK_ROOT_NODES, NUMBERING_ENABLED_KEY, ROOT_NODES_KEY,
} from '../editorContext'

const props = defineProps<{
  node: { attrs: Record<string, unknown> }
  updateAttributes: (attrs: Record<string, unknown>) => void
  deleteNode: () => void
  selected?: boolean
}>()

const numberingEnabled = inject(NUMBERING_ENABLED_KEY, FALLBACK_NUMBERING)
const rootNodes = inject(ROOT_NODES_KEY, FALLBACK_ROOT_NODES)

const FIELD_LABELS: Record<AnswerFieldKey, string> = { answer: '答案', thinking: '思路', analysis: '解析', summary: '小结' }

const detail = computed(() => detailPropsOf({ props: props.node.attrs.props } as EditorNode))

const scopeModel = computed<DetailScope>({
  get: () => detail.value.scope,
  set: (v) => props.updateAttributes({ props: { ...detail.value, scope: v, fields: { ...detail.value.fields } } }),
})
function toggleGlobalField(key: AnswerFieldKey, value: boolean) {
  props.updateAttributes({ props: { ...detail.value, fields: { ...detail.value.fields, [key]: value } } })
}

// 作用域内题目（保序）：all=全篇；before=模块之前。
const scopedQuestions = computed<EditorNode[]>(() => {
  const nodes = rootNodes.value as unknown as EditorNode[]
  const uid = props.node.attrs.uid as string | undefined
  const idx = uid ? nodes.findIndex((n) => n.id === uid) : -1
  const before = detail.value.scope === 'before'
  return nodes.filter((n, i) => n.nodeType === 'question' && (!before || (idx >= 0 && i < idx)))
})
const anyFieldOn = computed(() => ANSWER_FIELD_KEYS.some((k) => detail.value.fields[k]))
// 可见字段与题目无关（全模块共享 detail.fields），预先算好便于判断首个字段行需拼上题号。
const visibleFieldKeys = computed(() => ANSWER_FIELD_KEYS.filter((k) => detail.value.fields[k]))
</script>

<template>
  <NodeViewWrapper
    data-composition-block
    class="composition-module group relative my-2 rounded-lg border border-transparent px-3 py-3 transition-colors hover:border-primary/30 hover:bg-primary/5 focus-within:border-primary/30 focus-within:bg-primary/5"
    :class="selected ? 'border-primary/30 bg-primary/5' : ''"
    contenteditable="false"
  >
    <!-- 浮动控制条：静息态所见即所得（只有答案派生结果），悬浮/选中/聚焦时才浮现编辑控件 -->
    <div
      class="absolute -top-3 right-2 z-10 flex items-center gap-1 rounded-md border bg-card px-1.5 py-0.5 shadow-sm transition-opacity"
      :class="selected ? 'opacity-100' : 'opacity-0 group-hover:opacity-100 focus-within:opacity-100'"
    >
      <ListChecks class="h-3.5 w-3.5 text-primary" />
      <span class="text-[11px] font-semibold text-primary">参考答案</span>
      <span class="ml-2 text-[11px] text-muted-foreground">范围</span>
      <Select v-model="scopeModel">
        <SelectTrigger class="h-6 w-32 text-[11px]"><SelectValue /></SelectTrigger>
        <SelectContent>
          <SelectItem value="all">全篇题目</SelectItem>
          <SelectItem value="before">此模块之前的题目</SelectItem>
        </SelectContent>
      </Select>
      <Popover>
        <PopoverTrigger as-child>
          <Button variant="ghost" size="sm" class="h-6 gap-1 px-2 text-[11px]"><Eye class="h-3 w-3" /> 显示</Button>
        </PopoverTrigger>
        <PopoverContent align="end" class="w-52 space-y-2" data-rich-overlay>
          <p class="text-xs font-medium text-muted-foreground">显示字段</p>
          <label v-for="key in ANSWER_FIELD_KEYS" :key="key" class="flex items-center justify-between gap-2 text-xs">
            {{ FIELD_LABELS[key] }}
            <Switch :model-value="detail.fields[key]" @update:model-value="toggleGlobalField(key, $event)" />
          </label>
        </PopoverContent>
      </Popover>
      <Button variant="ghost" size="icon" class="h-6 w-6 text-destructive hover:text-destructive" title="删除模块" @click="deleteNode()">
        <Trash2 class="h-3.5 w-3.5" />
      </Button>
    </div>

    <div class="space-y-3">
      <p v-if="!scopedQuestions.length" class="rounded-md border border-dashed py-6 text-center text-xs text-muted-foreground">
        此范围内暂无题目。
      </p>
      <p v-else-if="!anyFieldOn" class="text-center text-xs text-muted-foreground">未选择要显示的字段。</p>
      <!-- 与真实导出（docx/latex）一致的排版：题号列固定宽度（2 栏网格），各字段行的内容起点严格对齐；
      【标签】与内容同色，不用灰色区分 -->
      <div v-for="q in scopedQuestions" :key="q.id" class="space-y-0.5 text-sm">
        <div v-if="!q.questionContent" class="flex items-center gap-2 text-xs text-destructive">
          <AlertTriangle class="h-3.5 w-3.5" /> 题目内容不可用（#{{ q.questionId }}）
        </div>
        <template v-else>
          <div
            v-for="(key, idx) in visibleFieldKeys" :key="key"
            class="grid grid-cols-[1.75rem_1fr] leading-relaxed"
          >
            <span class="font-medium">{{ idx === 0 && numberingEnabled && questionNumberOf(q) ? `${questionNumberOf(q)}.` : '' }}</span>
            <div>
              <span class="font-medium">【{{ FIELD_LABELS[key] }}】</span>
              <AnswerDisplay v-if="key === 'answer'" :answer="q.questionContent.answer" :options="q.questionContent.options" class="inline" />
              <RichContent v-else :content="q.questionContent[key]" class="inline [&_p]:my-0 [&_p]:inline" empty-text="（空）" />
            </div>
          </div>
        </template>
      </div>
    </div>
  </NodeViewWrapper>
</template>
