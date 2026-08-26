<script setup lang="ts">
import { computed, ref } from 'vue'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Plus, Type, Heading, FileQuestion, SeparatorHorizontal, ListChecks, RefreshCw, Loader2,
} from '@lucide/vue'
import BlockItem from './BlockItem.vue'
import QuestionDetailsModuleEditor from './QuestionDetailsModuleEditor.vue'
import QuestionPicker from './QuestionPicker.vue'
import {
  collectStaleQuestionNodeIds, createHeadingNode, createPageBreakNode, createQuestionNode,
  createRichTextNode, DETAIL_PRESETS, insertModuleCustomBefore, insertRootNodeAfter,
  moveModuleCustomChild, moveRootNode, normalizeDocument, patchNode, questionNodeStatus,
  removeModuleCustomChild, removeRootNode,
} from '@/lib/compositionDocument'
import type { EditorDocument, EditorNode } from '@/lib/compositionDocument'
import type { QuestionRevisionStatus } from '@/types/composition'
import type { Question } from '@/types'

const props = defineProps<{
  document: EditorDocument
  subjectId: number | null
  // 题目版本状态（question_id → 实时 revision/可用性），由页面按需刷新。
  questionStatus?: Map<number, QuestionRevisionStatus>
  // 有未保存修改时禁止同步，避免覆盖本地内容。
  syncDisabled?: boolean
  syncing?: boolean
}>()

const emit = defineEmits<{
  'update:document': [doc: EditorDocument]
  // 请求同步指定 question 节点 UUID（“同步此题”传一个，“同步全部”传多个）。
  sync: [nodeIds: string[]]
}>()

const pickerOpen = ref(false)

function setDocument(next: EditorDocument) {
  emit('update:document', next)
}

// question 节点 UUID → 节点，供模块编辑器解析冻结题目内容。
const questionNodeMap = computed(() => {
  const map = new Map<string, EditorNode>()
  for (const node of props.document.nodes) {
    if (node.nodeType === 'question') map.set(node.id, node)
  }
  return map
})

type AddKind = 'rich_text' | 'heading' | 'question' | 'page_break' | 'module_reference' | 'module_analysis'

function addNode(kind: AddKind) {
  const at = props.document.nodes.length - 1
  if (kind === 'question') {
    pickerOpen.value = true
    return
  }
  let node: EditorNode
  if (kind === 'rich_text') node = createRichTextNode()
  else if (kind === 'heading') node = createHeadingNode()
  else if (kind === 'page_break') node = createPageBreakNode()
  else if (kind === 'module_reference') node = DETAIL_PRESETS.reference()
  else node = DETAIL_PRESETS.analysis()
  setDocument(insertRootNodeAfter(props.document, at, node))
}

function onQuestionSelected(question: Question) {
  setDocument(insertRootNodeAfter(props.document, props.document.nodes.length - 1, createQuestionNode(question)))
}

// --- root 层操作 ---
function onPatch(id: string, patch: Partial<Pick<EditorNode, 'content' | 'props'>>) {
  // module scope/fields 变化需立即重派生 answer_item，故 patch 后统一规范化。
  setDocument(normalizeDocument(patchNode(props.document, id, patch)))
}

function onMove(index: number, direction: 'up' | 'down') {
  setDocument(moveRootNode(props.document, index, direction))
}

function onRemove(id: string) {
  setDocument(removeRootNode(props.document, id))
}

// --- module 子层操作 ---
function onPatchChild(id: string, patch: Partial<Pick<EditorNode, 'content' | 'props'>>) {
  setDocument(normalizeDocument(patchNode(props.document, id, patch)))
}

function onMoveChild(moduleId: string, childId: string, direction: 'up' | 'down') {
  setDocument(moveModuleCustomChild(props.document, moduleId, childId, direction))
}

function onRemoveChild(moduleId: string, childId: string) {
  setDocument(removeModuleCustomChild(props.document, moduleId, childId))
}

function onAddCustom(moduleId: string, answerItemId: string | null, nodeType: 'heading' | 'rich_text') {
  const node = nodeType === 'heading' ? createHeadingNode() : createRichTextNode()
  setDocument(insertModuleCustomBefore(props.document, moduleId, answerItemId, node))
}

// --- 版本状态（stale / deleted）：仅来自状态 API，绝不拉取实时题目内容渲染 ---
function statusFor(node: EditorNode): QuestionRevisionStatus | null {
  if (node.questionId == null) return null
  return props.questionStatus?.get(node.questionId) ?? null
}

function isStale(node: EditorNode): boolean {
  return questionNodeStatus(node, statusFor(node)).stale
}

function isDeleted(node: EditorNode): boolean {
  return questionNodeStatus(node, statusFor(node)).deleted
}

const staleNodeIds = computed(() =>
  collectStaleQuestionNodeIds(props.document, props.questionStatus ?? new Map()),
)
const hasStale = computed(() => staleNodeIds.value.length > 0)

function syncOne(node: EditorNode) {
  if (props.syncDisabled || props.syncing) return
  emit('sync', [node.id])
}

function syncAll() {
  if (props.syncDisabled || props.syncing || staleNodeIds.value.length === 0) return
  emit('sync', staleNodeIds.value)
}

defineExpose({ hasStale })
</script>

<template>
  <div class="flex flex-col gap-3">
    <!-- 同步全部：存在过期题目时出现；dirty 时禁用以免覆盖本地 -->
    <div
      v-if="hasStale"
      class="flex items-center gap-3 rounded-md border border-amber-400 bg-amber-50 px-4 py-2.5 text-sm dark:border-amber-700 dark:bg-amber-900/20"
    >
      <RefreshCw class="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
      <span class="flex-1">有 {{ staleNodeIds.length }} 道题目在题库中已更新（当前仍显示定格的旧内容）。</span>
      <Button
        size="sm" variant="outline"
        :disabled="syncDisabled || syncing"
        :title="syncDisabled ? '请先保存未保存的修改' : '把所有过期题目更新为题库最新内容'"
        @click="syncAll"
      >
        <Loader2 v-if="syncing" class="mr-2 h-4 w-4 animate-spin" />
        <RefreshCw v-else class="mr-2 h-4 w-4" />
        同步全部
      </Button>
    </div>

    <div v-if="document.nodes.length === 0" class="rounded-lg border border-dashed py-16 text-center">
      <p class="mb-4 text-sm text-muted-foreground">画布还是空的，添加第一个块开始编辑。</p>
      <DropdownMenu>
        <DropdownMenuTrigger as-child>
          <Button variant="outline">
            <Plus class="mr-2 h-4 w-4" /> 添加块
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="center">
          <DropdownMenuItem @click="addNode('rich_text')"><Type class="mr-2 h-4 w-4" /> 文本</DropdownMenuItem>
          <DropdownMenuItem @click="addNode('heading')"><Heading class="mr-2 h-4 w-4" /> 标题</DropdownMenuItem>
          <DropdownMenuItem @click="addNode('question')"><FileQuestion class="mr-2 h-4 w-4" /> 题目</DropdownMenuItem>
          <DropdownMenuItem @click="addNode('page_break')"><SeparatorHorizontal class="mr-2 h-4 w-4" /> 分页</DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuLabel class="text-xs">答案汇总模块</DropdownMenuLabel>
          <DropdownMenuItem @click="addNode('module_reference')"><ListChecks class="mr-2 h-4 w-4" /> 参考答案</DropdownMenuItem>
          <DropdownMenuItem @click="addNode('module_analysis')"><ListChecks class="mr-2 h-4 w-4" /> 答案与解析</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>

    <template v-else>
      <template v-for="(node, index) in document.nodes" :key="node.id">
        <QuestionDetailsModuleEditor
          v-if="node.nodeType === 'question_details'"
          :node="node"
          :index="index"
          :total="document.nodes.length"
          :question-node-map="questionNodeMap"
          @patch="onPatch(node.id, $event)"
          @move="onMove(index, $event)"
          @remove="onRemove(node.id)"
          @patch-child="onPatchChild"
          @move-child="(childId: string, dir: 'up' | 'down') => onMoveChild(node.id, childId, dir)"
          @remove-child="(childId: string) => onRemoveChild(node.id, childId)"
          @add-custom="(answerItemId: string | null, nodeType: 'heading' | 'rich_text') => onAddCustom(node.id, answerItemId, nodeType)"
        />
        <BlockItem
          v-else
          :node="node"
          :index="index"
          :total="document.nodes.length"
          :stale="isStale(node)"
          :deleted="isDeleted(node)"
          :sync-disabled="syncDisabled || syncing"
          @patch="onPatch(node.id, $event)"
          @move="onMove(index, $event)"
          @remove="onRemove(node.id)"
          @sync="syncOne(node)"
        />
      </template>

      <div class="flex justify-center pt-1">
        <DropdownMenu>
          <DropdownMenuTrigger as-child>
            <Button variant="outline" size="sm">
              <Plus class="mr-2 h-4 w-4" /> 添加块
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="center">
            <DropdownMenuItem @click="addNode('rich_text')"><Type class="mr-2 h-4 w-4" /> 文本</DropdownMenuItem>
            <DropdownMenuItem @click="addNode('heading')"><Heading class="mr-2 h-4 w-4" /> 标题</DropdownMenuItem>
            <DropdownMenuItem @click="addNode('question')"><FileQuestion class="mr-2 h-4 w-4" /> 题目</DropdownMenuItem>
            <DropdownMenuItem @click="addNode('page_break')"><SeparatorHorizontal class="mr-2 h-4 w-4" /> 分页</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuLabel class="text-xs">答案汇总模块</DropdownMenuLabel>
            <DropdownMenuItem @click="addNode('module_reference')"><ListChecks class="mr-2 h-4 w-4" /> 参考答案</DropdownMenuItem>
            <DropdownMenuItem @click="addNode('module_analysis')"><ListChecks class="mr-2 h-4 w-4" /> 答案与解析</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </template>

    <QuestionPicker
      v-model:open="pickerOpen"
      :subject-id="subjectId"
      @select="onQuestionSelected"
    />
  </div>
</template>
