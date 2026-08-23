import type { Component } from 'vue'
import type { Editor } from '@tiptap/vue-3'
import { Bold, Italic, Underline, Superscript, Subscript, RemoveFormatting } from '@lucide/vue'

export interface ToolbarItem {
    label: string
    icon: Component
    action: () => void
    isActive?: () => boolean
    disabled?: () => boolean
}

/** 行内标记按钮（选中才有意义），工具栏与气泡菜单共用。 */
export function getInlineFormatItems(editor: Editor): ToolbarItem[] {
    return [
        {
            label: '加粗',
            icon: Bold,
            action: () => editor.chain().focus().toggleBold().run(),
            isActive: () => editor.isActive('bold'),
        },
        {
            label: '斜体',
            icon: Italic,
            action: () => editor.chain().focus().toggleItalic().run(),
            isActive: () => editor.isActive('italic'),
        },
        {
            label: '下划线',
            icon: Underline,
            action: () => editor.chain().focus().toggleUnderline().run(),
            isActive: () => editor.isActive('underline'),
        },
        {
            label: '上标',
            icon: Superscript,
            action: () => editor.chain().focus().toggleSuperscript().run(),
            isActive: () => editor.isActive('superscript'),
        },
        {
            label: '下标',
            icon: Subscript,
            action: () => editor.chain().focus().toggleSubscript().run(),
            isActive: () => editor.isActive('subscript'),
        },
        {
            label: '清除格式',
            icon: RemoveFormatting,
            action: () => editor.chain().focus().unsetAllMarks().clearNodes().run(),
        },
    ]
}
