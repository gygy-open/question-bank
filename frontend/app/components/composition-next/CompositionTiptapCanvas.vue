<script setup lang="ts">
// 组稿「单一 tiptap 文档」画布：连续编辑 + DragHandle 拖块 + NodeRange 跨块选区，
// 并镜像 RichEditor 的外围（Math/Blank 就地编辑、斜杠命令、工具栏、气泡菜单、图片）。
import { ref, computed, watch, provide, nextTick } from 'vue'
import type { EditorView } from '@tiptap/pm/view'
import type { Node as PMNode } from '@tiptap/pm/model'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import Placeholder from '@tiptap/extension-placeholder'
import { NodeRange } from '@tiptap/extension-node-range'
import { DragHandle } from '@tiptap/extension-drag-handle-vue-3'
import { GripVertical, FileQuestion, Files, ListChecks, RefreshCw, Loader2, Copy, Trash2 } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import RichEditorToolbar from '@/components/rich-editor/RichEditorToolbar.vue'
import RichEditorBubbleMenu from '@/components/rich-editor/RichEditorBubbleMenu.vue'
import RichEditorMathPopover from '@/components/rich-editor/RichEditorMathPopover.vue'
import RichEditorBlankPopover from '@/components/rich-editor/RichEditorBlankPopover.vue'
import QuestionPicker from '@/components/composition/QuestionPicker.vue'
import CompositionPicker from '@/components/composition/CompositionPicker.vue'
import { useImageUpload } from '@/components/rich-editor/useImageUpload'
import { ResetFormatOnEnter } from '@/components/rich-editor/resetFormatExtension'
import { createMathNodeView, requestMathAutofocus } from '@/components/rich-editor/mathFieldExtensions'
import { createBlankNodeView } from '@/components/rich-editor/blankNodeView'
import { MATH_EDITOR_KEY, type OpenMathEditorParams } from '@/components/rich-editor/mathEditorKey'
import { BLANK_EDITOR_KEY, type OpenBlankEditorParams } from '@/components/rich-editor/blankEditorKey'
import {
  cloneNodesForInsert, collectStaleQuestionNodeIds, createQuestionNode, DETAIL_PRESETS,
  documentFromNodes, type EditorDocument,
} from '@/lib/compositionDocument'
import type { CompositionDetail, CompositionScope, Question } from '@/types'
import type { AnswerFieldKey, QuestionRevisionStatus } from '@/types/composition'
import { getCompositionExtensions } from './schema'
import { CompositionSlashCommand } from './CompositionSlashCommand'
import { editorDocumentToPmDoc, pmDocToEditorDocument } from './convert'
import {
  DISPLAY_FIELDS_KEY, NUMBERING_ENABLED_KEY, QUESTION_STATUS_KEY, ROOT_NODES_KEY,
  SCORING_ENABLED_KEY, SYNC_DISABLED_KEY, SYNC_QUESTIONS_KEY, defaultDisplayFields,
  type EditorNodeLike,
} from './editorContext'

const WORD_MATH_HTML_RE = /<\s*m:oMath|<\s*math[\s/>]/i

const model = defineModel<EditorDocument>('document', { required: true })
const props = defineProps<{
  subjectId?: number | null
  scope?: CompositionScope | null
  // 插入稿件选择器排除自身。
  compositionId?: number | null
  // 全局显示设置（供题目 NodeView 注入）。
  numberingEnabled?: boolean
  scoringEnabled?: boolean
  globalDisplayFields?: Record<AnswerFieldKey, boolean>
  // 题目版本状态与同步禁用/进行中。
  questionStatus?: Map<number, QuestionRevisionStatus>
  syncDisabled?: boolean
  syncing?: boolean
}>()
const emit = defineEmits<{ sync: [nodeIds: string[]] }>()

provide(NUMBERING_ENABLED_KEY, computed(() => props.numberingEnabled ?? false))
provide(SCORING_ENABLED_KEY, computed(() => props.scoringEnabled ?? false))
provide(DISPLAY_FIELDS_KEY, computed(() => props.globalDisplayFields ?? defaultDisplayFields()))
provide(QUESTION_STATUS_KEY, computed(() => props.questionStatus ?? new Map()))
provide(SYNC_DISABLED_KEY, computed(() => (props.syncDisabled ?? false) || (props.syncing ?? false)))
provide(SYNC_QUESTIONS_KEY, (ids: string[]) => emit('sync', ids))
// 有序根节点（含题目快照），供模块按 scope + 位置实时派生答案。
provide(ROOT_NODES_KEY, computed(() => model.value.nodes as unknown as EditorNodeLike[]))

const staleNodeIds = computed(() =>
  collectStaleQuestionNodeIds(model.value, props.questionStatus ?? new Map()),
)

const { uploadImage } = useImageUpload()
const fileInputRef = ref<HTMLInputElement | null>(null)

async function insertImageFile(file: File) {
  try {
    const url = await uploadImage(file)
    editor.value?.chain().focus().setImage({ src: url }).run()
  } catch (error) {
    console.error(error)
  }
}

function triggerImagePicker() {
  fileInputRef.value?.click()
}

function onFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (file) insertImageFile(file)
  target.value = ''
}

// 含 Word 公式（OMML/MathML）的粘贴：转换器异步加载，先锁定插入区间再按区间插入。
async function handleMathPaste(html: string, from: number, to: number) {
  try {
    const { wordHtmlToTiptapHtml } = await import('@/components/rich-editor/wordMathPaste')
    const converted = wordHtmlToTiptapHtml(html)
    const size = editor.value?.state.doc.content.size ?? 0
    editor.value
      ?.chain()
      .focus()
      .insertContentAt({ from: Math.min(from, size), to: Math.min(to, size) }, converted)
      .run()
  } catch (error) {
    console.error(error)
  }
}

function openInsertMath(isBlock: boolean) {
  const type = isBlock ? 'blockMath' : 'inlineMath'
  requestMathAutofocus()
  editor.value?.chain().focus().insertContent({ type, attrs: { latex: '' } }).run()
}

// --- 公式就地编辑浮层（math-field 渲染在 ProseMirror 之外，避开焦点冲突） ---
const mathEditOpen = ref(false)
const mathEditLatex = ref('')
const mathEditIsBlock = ref(false)
const mathEditPos = ref<number | null>(null)
const mathEditAnchor = ref<HTMLElement | null>(null)

function openMathEditor(params: OpenMathEditorParams) {
  mathEditPos.value = params.pos
  mathEditIsBlock.value = params.isBlock
  mathEditLatex.value = params.latex
  mathEditAnchor.value = params.anchorEl
  // 先关再开，强制浮层在 open false→true 跳变时按当前几何重新定位（同一锚点再次点击也生效）。
  mathEditOpen.value = false
  nextTick(() => { mathEditOpen.value = true })
}
provide(MATH_EDITOR_KEY, openMathEditor)

function removeMathAt(pos: number, isBlock: boolean) {
  const chain = editor.value?.chain().focus()
  if (!chain) return
  if (isBlock) chain.deleteBlockMath({ pos }).run()
  else chain.deleteInlineMath({ pos }).run()
}

function submitMath(latex: string) {
  const pos = mathEditPos.value
  mathEditOpen.value = false
  if (pos == null) return
  if (!latex) {
    removeMathAt(pos, mathEditIsBlock.value)
    return
  }
  const chain = editor.value?.chain().focus()
  if (!chain) return
  if (mathEditIsBlock.value) chain.updateBlockMath({ latex, pos }).run()
  else chain.updateInlineMath({ latex, pos }).run()
}

function deleteMath() {
  const pos = mathEditPos.value
  mathEditOpen.value = false
  if (pos != null) removeMathAt(pos, mathEditIsBlock.value)
}

function cancelMath() {
  mathEditOpen.value = false
  // 取消时若原本是空公式（新插入未填），删除占位节点。
  if (!mathEditLatex.value && mathEditPos.value != null) removeMathAt(mathEditPos.value, mathEditIsBlock.value)
}

// --- 填空长度调整浮层 ---
const blankEditOpen = ref(false)
const blankEditPos = ref<number | null>(null)
const blankEditWidth = ref(4)
const blankEditAnchor = ref<HTMLElement | null>(null)

function openBlankEditor(params: OpenBlankEditorParams) {
  blankEditPos.value = params.pos
  blankEditWidth.value = params.widthEm
  blankEditAnchor.value = params.anchorEl
  blankEditOpen.value = true
}
provide(BLANK_EDITOR_KEY, openBlankEditor)

function updateBlankWidth(widthEm: number) {
  const pos = blankEditPos.value
  if (pos == null) return
  blankEditWidth.value = widthEm
  editor.value?.chain().setBlankWidth(pos, widthEm).run()
}

function removeBlank() {
  const pos = blankEditPos.value
  blankEditOpen.value = false
  if (pos != null) editor.value?.chain().focus().removeBlank(pos).run()
}

function closeBlankEditor() {
  blankEditOpen.value = false
}

function insertBlank() {
  editor.value?.chain().focus().insertBlank().run()
}

function insertTable(options: { rows: number; cols: number; withHeaderRow: boolean }) {
  editor.value?.chain().focus().insertTable(options).run()
}

// --- 题目 / 稿件插入 ---
const questionPickerOpen = ref(false)
const compositionPickerOpen = ref(false)
// 打开 picker 瞬间捕获插入位置：picker 是模态框，编辑器会失焦，focus() 无法可靠回到斜杠处。
const pendingInsertPos = ref<number | null>(null)

function openQuestionPicker() {
  pendingInsertPos.value = editor.value?.state.selection.from ?? null
  questionPickerOpen.value = true
}

function openCompositionPicker() {
  pendingInsertPos.value = editor.value?.state.selection.from ?? null
  compositionPickerOpen.value = true
}

// 把 EditorNode 行转为 PM 块并插入到捕获位置（缺省落到光标）；uid 由 uniqueId 插件去重。
function insertRows(nodes: EditorDocument['nodes']) {
  const pm = editorDocumentToPmDoc({ nodes })
  const content = pm.content ?? []
  const chain = editor.value?.chain().focus()
  if (!chain) return
  if (pendingInsertPos.value != null) chain.insertContentAt(pendingInsertPos.value, content).run()
  else chain.insertContent(content).run()
  pendingInsertPos.value = null
}

function onQuestionsSelected(questions: Question[]) {
  insertRows(questions.map((q) => createQuestionNode(q)))
}

function onCompositionSelected(detail: CompositionDetail) {
  insertRows(cloneNodesForInsert(documentFromNodes(detail.nodes).nodes))
}

// 在光标处插入参考答案模块（预设的“参考答案”标题会被上提为模块前的顶层块；答案由模块按 scope 派生）。
function insertModule() {
  insertRows([DETAIL_PRESETS.summary()])
}

// 拖拽手柄当前指向的顶层块（由 DragHandle 的 onNodeChange 更新），用于块操作菜单。
const handleNode = ref<PMNode | null>(null)
const handlePos = ref(-1)
function onHandleNodeChange(data: { node: PMNode | null; pos: number }) {
  handleNode.value = data.node
  handlePos.value = data.pos
}
function deleteHandleNode() {
  const node = handleNode.value
  const pos = handlePos.value
  if (!node || pos < 0 || !editor.value) return
  editor.value.chain().focus().deleteRange({ from: pos, to: pos + node.nodeSize }).run()
}
function duplicateHandleNode() {
  const node = handleNode.value
  const pos = handlePos.value
  if (!node || pos < 0 || !editor.value) return
  const json = node.toJSON()
  if (json?.attrs) delete json.attrs.uid // 让 UniqueId 重新分配，避免 uid 冲突
  editor.value.chain().focus().insertContentAt(pos + node.nodeSize, json).run()
}

const editor = useEditor({
  content: editorDocumentToPmDoc(model.value),
  extensions: [
    ...getCompositionExtensions({
      imageResizable: true,
      mathNodeView: createMathNodeView(),
      blankNodeView: createBlankNodeView(),
    }),
    ResetFormatOnEnter,
    // 按住 Mod（Cmd/Ctrl）拖拽跨块选区；配合 DragHandle 做可视化整块拖动。
    NodeRange,
    Placeholder.configure({ placeholder: '输入内容，或输入 “/” 唤起命令菜单…', showOnlyCurrent: false }),
    CompositionSlashCommand.configure({
      onImageSelect: triggerImagePicker,
      onInsertMath: openInsertMath,
      onInsertQuestion: openQuestionPicker,
      onInsertComposition: openCompositionPicker,
      onInsertModule: insertModule,
    }),
  ],
  editorProps: {
    attributes: {
      class: 'composition-doc prose prose-sm dark:prose-invert max-w-none focus:outline-none min-h-[240px] px-3 py-2 pl-8',
    },
    handleDrop(_view: EditorView, event: DragEvent) {
      const files = event.dataTransfer?.files
      if (files?.length) {
        const image = Array.from(files).find((f) => f.type.startsWith('image/'))
        if (image) {
          event.preventDefault()
          insertImageFile(image)
          return true
        }
      }
      return false
    },
    handlePaste(view: EditorView, event: ClipboardEvent) {
      const html = event.clipboardData?.getData('text/html')
      if (html && WORD_MATH_HTML_RE.test(html)) {
        event.preventDefault()
        const { from, to } = view.state.selection
        handleMathPaste(html, from, to)
        return true
      }
      const items = event.clipboardData?.items
      if (items) {
        for (const item of items) {
          if (item.type.startsWith('image/')) {
            const file = item.getAsFile()
            if (file) {
              event.preventDefault()
              insertImageFile(file)
              return true
            }
          }
        }
      }
      return false
    },
  },
  onUpdate: ({ editor: e }) => {
    model.value = pmDocToEditorDocument(e.getJSON() as never)
  },
})

// 外部替换文档（加载/保存回填）时重建编辑器内容；与本地编辑一致时不 setContent，避免打断。
watch(
  () => model.value,
  (next) => {
    const inst = editor.value
    if (!inst) return
    const current = pmDocToEditorDocument(inst.getJSON() as never)
    if (JSON.stringify(current) === JSON.stringify(next)) return
    inst.commands.setContent(editorDocumentToPmDoc(next), { emitUpdate: false })
  },
)
</script>

<template>
  <div class="composition-tiptap-canvas rounded-md border border-border bg-background">
    <div
      v-if="staleNodeIds.length"
      class="flex items-center gap-3 rounded-t-md border-b border-amber-400 bg-amber-50 px-4 py-2.5 text-sm dark:border-amber-700 dark:bg-amber-900/20"
    >
      <RefreshCw class="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
      <span class="flex-1">有 {{ staleNodeIds.length }} 道题目在题库中已更新（当前仍显示定格的旧内容）。</span>
      <Button
        size="sm" variant="outline"
        :disabled="(props.syncDisabled ?? false) || (props.syncing ?? false)"
        :title="props.syncDisabled ? '请先保存未保存的修改' : '把所有过期题目更新为题库最新内容'"
        @click="emit('sync', staleNodeIds)"
      >
        <Loader2 v-if="props.syncing" class="mr-2 h-4 w-4 animate-spin" />
        <RefreshCw v-else class="mr-2 h-4 w-4" />
        同步全部
      </Button>
    </div>

    <div v-if="editor" class="sticky top-0 z-30 rounded-t-md bg-background">
      <RichEditorToolbar
        :editor="editor"
        allow-heading
        @image="triggerImagePicker"
        @math="openInsertMath"
        @blank="insertBlank"
        @table="insertTable"
      >
        <Tooltip>
          <TooltipTrigger as-child>
            <Button type="button" variant="ghost" size="icon" class="size-8" @mousedown.prevent @click="openQuestionPicker">
              <FileQuestion class="size-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>插入题目</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger as-child>
            <Button type="button" variant="ghost" size="icon" class="size-8" @mousedown.prevent @click="openCompositionPicker">
              <Files class="size-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>插入稿件</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger as-child>
            <Button type="button" variant="ghost" size="icon" class="size-8" @mousedown.prevent @click="insertModule">
              <ListChecks class="size-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>插入参考答案</TooltipContent>
        </Tooltip>
      </RichEditorToolbar>
    </div>

    <div class="relative overflow-hidden rounded-b-md">
      <DragHandle
        v-if="editor"
        :editor="editor"
        class="composition-drag-handle"
        :on-node-change="onHandleNodeChange"
      >
        <DropdownMenu>
          <DropdownMenuTrigger as-child>
            <button type="button" class="flex size-full items-center justify-center" aria-label="块操作">
              <GripVertical class="size-4 text-muted-foreground" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" side="bottom" class="w-40">
            <DropdownMenuItem @click="duplicateHandleNode">
              <Copy class="mr-2 size-4" />复制
            </DropdownMenuItem>
            <DropdownMenuItem class="text-destructive focus:text-destructive" @click="deleteHandleNode">
              <Trash2 class="mr-2 size-4" />删除
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </DragHandle>
      <EditorContent :editor="editor" />
    </div>

    <RichEditorBubbleMenu v-if="editor" :editor="editor" />

    <RichEditorMathPopover
      :open="mathEditOpen"
      :latex="mathEditLatex"
      :display-mode="mathEditIsBlock"
      :anchor-el="mathEditAnchor"
      :can-delete="!!mathEditLatex"
      @submit="submitMath"
      @delete="deleteMath"
      @cancel="cancelMath"
    />

    <RichEditorBlankPopover
      :open="blankEditOpen"
      :width-em="blankEditWidth"
      :anchor-el="blankEditAnchor"
      @update="updateBlankWidth"
      @delete="removeBlank"
      @close="closeBlankEditor"
    />

    <input ref="fileInputRef" type="file" accept="image/*" class="hidden" @change="onFileChange" />

    <QuestionPicker
      v-model:open="questionPickerOpen"
      :subject-id="props.subjectId ?? null"
      @select="onQuestionsSelected"
    />
    <CompositionPicker
      v-model:open="compositionPickerOpen"
      :subject-id="props.subjectId ?? null"
      :exclude-composition-id="props.compositionId"
      :exclude-scope="props.scope"
      @select="onCompositionSelected"
    />
  </div>
</template>

<style scoped>
.composition-drag-handle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.5rem;
  height: 1.5rem;
  border-radius: 0.25rem;
  cursor: grab;
  transition: background-color 0.15s ease;
}

.composition-drag-handle:active {
  cursor: grabbing;
}

:deep(.ProseMirror) {
  outline: none;
}

:deep(.ProseMirror .is-empty::before) {
  content: attr(data-placeholder);
  color: var(--muted-foreground);
  float: left;
  height: 0;
  pointer-events: none;
}

:deep(.composition-page-break) {
  height: 0;
  border-top: 2px dashed var(--border);
  margin: 1rem 0;
}

/* 图片缩放手柄：tiptap 内置 ResizableNodeView 只写 data-* 属性，不带任何可见样式 */
:deep([data-resize-handle]) {
  width: 10px;
  height: 10px;
  background: var(--background);
  border: 2px solid var(--primary);
  border-radius: 2px;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.15s ease;
}

:deep([data-resize-wrapper]:hover [data-resize-handle]),
:deep(.ProseMirror-selectednode [data-resize-handle]) {
  opacity: 1;
  pointer-events: auto;
}

:deep([data-resize-handle='top-left']),
:deep([data-resize-handle='bottom-right']) {
  cursor: nwse-resize;
}

:deep([data-resize-handle='top-right']),
:deep([data-resize-handle='bottom-left']) {
  cursor: nesw-resize;
}

:deep(.tableWrapper) {
  overflow-x: auto;
}

:deep(.ProseMirror table) {
  border-collapse: collapse;
  table-layout: fixed;
  width: 100%;
  overflow: hidden;
}

:deep(.ProseMirror td),
:deep(.ProseMirror th) {
  vertical-align: top;
  box-sizing: border-box;
  position: relative;
  border: 1px solid var(--border);
  padding: 0.35em 0.6em;
}

:deep(.ProseMirror td:not([data-colwidth])),
:deep(.ProseMirror th:not([data-colwidth])) {
  min-width: var(--default-cell-min-width);
}

:deep(.ProseMirror th) {
  background-color: var(--muted);
  font-weight: 600;
  text-align: left;
}

:deep(.ProseMirror .selectedCell)::after {
  content: '';
  position: absolute;
  inset: 0;
  background: color-mix(in srgb, var(--primary) 15%, transparent);
  pointer-events: none;
  z-index: 2;
}

:deep(.ProseMirror .column-resize-handle) {
  position: absolute;
  right: -2px;
  top: 0;
  bottom: 0;
  width: 4px;
  z-index: 20;
  background-color: var(--primary);
  pointer-events: none;
}

:deep(.ProseMirror.resize-cursor) {
  cursor: col-resize;
}
</style>
