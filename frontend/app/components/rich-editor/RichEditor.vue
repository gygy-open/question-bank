<script setup lang="ts">
import { ref, watch, provide } from 'vue'
import type { EditorView } from '@tiptap/pm/view'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import Placeholder from '@tiptap/extension-placeholder'
import { DragHandle } from '@tiptap/extension-drag-handle-vue-3'
import { GripVertical } from '@lucide/vue'
import { SlashCommand } from './SlashCommand'
import RichEditorToolbar from './RichEditorToolbar.vue'
import RichEditorBubbleMenu from './RichEditorBubbleMenu.vue'
import RichEditorMathPopover from './RichEditorMathPopover.vue'
import { useImageUpload } from './useImageUpload'
import { getSchemaExtensions } from './schemaExtensions'
import { ResetFormatOnEnter } from './resetFormatExtension'
import { createMathNodeView } from './mathFieldExtensions'
import { MATH_EDITOR_KEY, type OpenMathEditorParams } from './mathEditorKey'
import { isEmptyRichDoc } from './richDoc'
import type { RichDoc } from '@/types'

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

// 插入空公式节点，nodeView 挂载后会自动弹出 MathLive 编辑浮层。
function openInsertMath(isBlock: boolean) {
    const type = isBlock ? 'blockMath' : 'inlineMath'
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

function insertBlank() {
    editor.value?.chain().focus().insertBlank().run()
}

function insertTable() {
    editor.value
        ?.chain()
        .focus()
        .insertTable({ rows: 2, cols: 2, withHeaderRow: true })
        .run()
}

const editor = useEditor({
    content: model.value ?? '',
    extensions: [
        ...getSchemaExtensions({ mathNodeView: createMathNodeView() }),
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
        handlePaste(_view: EditorView, event: ClipboardEvent) {
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
            <DragHandle v-if="editor" :editor="editor" class="rich-editor__drag-handle">
                <GripVertical class="size-4 text-muted-foreground" />
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