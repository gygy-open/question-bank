<script setup lang="ts">
import { ref, watch, provide } from 'vue'
import type { EditorView } from '@tiptap/pm/view'
import type { Node as PMNode } from '@tiptap/pm/model'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import Placeholder from '@tiptap/extension-placeholder'
import { DragHandle } from '@tiptap/extension-drag-handle-vue-3'
import { GripVertical, Copy, Trash2 } from '@lucide/vue'
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { SlashCommand } from './SlashCommand'
import RichEditorToolbar from './RichEditorToolbar.vue'
import RichEditorBubbleMenu from './RichEditorBubbleMenu.vue'
import RichEditorMathPopover from './RichEditorMathPopover.vue'
import RichEditorBlankPopover from './RichEditorBlankPopover.vue'
import { useImageUpload } from './useImageUpload'
import { getSchemaExtensions } from './schemaExtensions'
import { ResetFormatOnEnter } from './resetFormatExtension'
import { createMathNodeView, requestMathAutofocus } from './mathFieldExtensions'
import { createBlankNodeView } from './blankNodeView'
import { MATH_EDITOR_KEY, type OpenMathEditorParams } from './mathEditorKey'
import { BLANK_EDITOR_KEY, type OpenBlankEditorParams } from './blankEditorKey'
import { isEmptyRichDoc } from './richDoc'
import type { RichDoc } from '@/types'

const WORD_MATH_HTML_RE = /<\s*m:oMath|<\s*math[\s/>]/i

const model = defineModel<RichDoc>({ default: null })
const props = withDefaults(
    defineProps<{ placeholder?: string; allowBlank?: boolean }>(),
    {
        placeholder: '输入内容，或输入 “/” 唤起命令菜单…',
        allowBlank: false,
    },
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
    if (file) {
        insertImageFile(file)
    }
    target.value = ''
}

/**
 * 处理含 Word 公式（OMML / MathML）的粘贴：转换器按需异步加载，
 * 因此在粘贴发生时先锁定插入区间（from/to），转换完成后按该区间插入，
 * 而非依赖异步返回后的当前光标位置。
 */
async function handleMathPaste(html: string, from: number, to: number) {
    try {
        const { wordHtmlToTiptapHtml } = await import('./wordMathPaste')
        const converted = wordHtmlToTiptapHtml(html)
        const size = editor.value?.state.doc.content.size ?? 0
        const start = Math.min(from, size)
        const end = Math.min(to, size)
        editor.value
            ?.chain()
            .focus()
            .insertContentAt({ from: start, to: end }, converted)
            .run()
    } catch (error) {
        console.error(error)
    }
}

// 插入空公式节点，nodeView 挂载后会自动进入行内编辑。
function openInsertMath(isBlock: boolean) {
    const type = isBlock ? 'blockMath' : 'inlineMath'
    requestMathAutofocus()
    editor.value?.chain().focus().insertContent({ type, attrs: { latex: '' } }).run()
}

// 公式编辑浮层状态（math-field 渲染在 ProseMirror 之外，避开焦点冲突）。
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
    mathEditOpen.value = true
}

provide(MATH_EDITOR_KEY, openMathEditor)

function removeMathAt(pos: number, isBlock: boolean) {
    const chain = editor.value?.chain().focus()
    if (!chain) {
        return
    }
    if (isBlock) {
        chain.deleteBlockMath({ pos }).run()
    } else {
        chain.deleteInlineMath({ pos }).run()
    }
}

function submitMath(latex: string) {
    const pos = mathEditPos.value
    mathEditOpen.value = false
    if (pos == null) {
        return
    }
    if (!latex) {
        removeMathAt(pos, mathEditIsBlock.value)
        return
    }
    const chain = editor.value?.chain().focus()
    if (!chain) {
        return
    }
    if (mathEditIsBlock.value) {
        chain.updateBlockMath({ latex, pos }).run()
    } else {
        chain.updateInlineMath({ latex, pos }).run()
    }
}

function deleteMath() {
    const pos = mathEditPos.value
    mathEditOpen.value = false
    if (pos != null) {
        removeMathAt(pos, mathEditIsBlock.value)
    }
}

function cancelMath() {
    mathEditOpen.value = false
    // 取消时若原本是空公式（新插入未填），删除占位节点
    if (!mathEditLatex.value && mathEditPos.value != null) {
        removeMathAt(mathEditPos.value, mathEditIsBlock.value)
    }
}

// 填空长度调整浮层：nodeView 点击时打开，脱离 ProseMirror 定位，适配 modal。
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
    if (pos == null) {
        return
    }
    blankEditWidth.value = widthEm
    editor.value?.chain().setBlankWidth(pos, widthEm).run()
}

function removeBlank() {
    const pos = blankEditPos.value
    blankEditOpen.value = false
    if (pos != null) {
        editor.value?.chain().focus().removeBlank(pos).run()
    }
}

function closeBlankEditor() {
    blankEditOpen.value = false
}

function insertBlank() {
    editor.value?.chain().focus().insertBlank().run()
}

function insertTable(options: { rows: number; cols: number; withHeaderRow: boolean }) {
    editor.value
        ?.chain()
        .focus()
        .insertTable(options)
        .run()
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
    editor.value.chain().focus().insertContentAt(pos + node.nodeSize, node.toJSON()).run()
}

const editor = useEditor({
    content: model.value ?? '',
    extensions: [
        ...getSchemaExtensions({
            mathNodeView: createMathNodeView(),
            blankNodeView: createBlankNodeView(),
            imageResizable: true,
        }),
        ResetFormatOnEnter,
        Placeholder.configure({
            placeholder: props.placeholder,
            showOnlyCurrent: false,
        }),
        SlashCommand.configure({
            onImageSelect: triggerImagePicker,
            onInsertMath: openInsertMath,
        }),
    ],
    editorProps: {
        attributes: {
            class: 'prose prose-sm dark:prose-invert max-w-none focus:outline-none min-h-[200px] px-3 py-2 pl-8',
        },
        handleDrop(_view: EditorView, event: DragEvent) {
            const files = event.dataTransfer?.files
            if (files?.length) {
                const image = Array.from(files).find((file) => file.type.startsWith('image/'))
                if (image) {
                    event.preventDefault()
                    insertImageFile(image)
                    return true
                }
            }
            return false
        },
        handlePaste(view: EditorView, event: ClipboardEvent) {
            // 先处理 Word 公式：若剪贴板 HTML 含 OMML/MathML，整次粘贴交由公式转换，
            // 避免下方 image 分支抢占（Word 常同时带公式图片与 HTML）。
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
    onUpdate: ({ editor }) => {
        const doc = editor.getJSON() as RichDoc
        model.value = isEmptyRichDoc(doc) ? null : doc
    },
})

watch(model, (value) => {
    if (!editor.value) {
        return
    }
    const current = editor.value.getJSON() as RichDoc
    // 空态互相等价（null 与“只有空段落”），不必重设
    if (isEmptyRichDoc(value) && isEmptyRichDoc(current)) {
        return
    }
    if (JSON.stringify(current) === JSON.stringify(value)) {
        return
    }
    // emitUpdate: false 防止触发 onUpdate 造成死循环
    editor.value.commands.setContent(value ?? '', { emitUpdate: false })
})
</script>

<template>
    <div class="rich-editor overflow-hidden rounded-md border border-border bg-background">
        <RichEditorToolbar v-if="editor" :editor="editor" :allow-blank="allowBlank" @image="triggerImagePicker" @math="openInsertMath" @blank="insertBlank" @table="insertTable" />

        <div class="relative">
            <DragHandle v-if="editor" :editor="editor" class="rich-editor__drag-handle" :on-node-change="onHandleNodeChange">
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

        <input
            ref="fileInputRef"
            type="file"
            accept="image/*"
            class="hidden"
            @change="onFileChange"
        />
    </div>
</template>

<style scoped>
.rich-editor__drag-handle {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 1.5rem;
    height: 1.5rem;
    border-radius: 0.25rem;
    cursor: grab;
    transition: background-color 0.15s ease;
}

.rich-editor__drag-handle:hover {
    background-color: var(--accent);
}

.rich-editor__drag-handle:active {
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

:deep(.ProseMirror img) {
    max-width: 100%;
    height: auto;
    border-radius: 0.375rem;
}

:deep(.ProseMirror .ProseMirror-selectednode) {
    outline: 2px solid var(--primary);
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

:deep(.ProseMirror .rich-blank) {
    display: inline-block;
    min-width: 2em;
    height: 1em;
    margin: 0 0.15em;
    border-bottom: 1px solid currentColor;
    vertical-align: baseline;
    cursor: pointer;
}

:deep(.ProseMirror .rich-blank:hover) {
    border-bottom-color: var(--primary);
    background-color: var(--accent);
}

/* prose 默认给列表项和其内段落留了较大间距，题库字段里收紧一些 */
:deep(.ProseMirror ul),
:deep(.ProseMirror ol) {
    margin-top: 0.25rem;
    margin-bottom: 0.25rem;
}

:deep(.ProseMirror li) {
    margin-top: 0.125rem;
    margin-bottom: 0.125rem;
}

:deep(.ProseMirror li > p) {
    margin-top: 0;
    margin-bottom: 0;
}

/* 公式节点：编辑态可点、hover 高亮，块公式独占一行居中 */
:deep(.tiptap-mathematics-render--editable) {
    cursor: pointer;
    border-radius: 4px;
}

:deep(.tiptap-mathematics-render--editable:hover) {
    background-color: var(--accent);
}

:deep(.tiptap-mathematics-render[data-type='block-math']) {
    margin: 0.5rem 0;
    text-align: center;
}

:deep(.tiptap-mathematics-render[data-type='inline-math']) {
    display: inline-block;
    padding: 0 2px;
}

:deep(.inline-math-error),
:deep(.block-math-error) {
    color: var(--destructive);
}
</style>

<style scoped></style>