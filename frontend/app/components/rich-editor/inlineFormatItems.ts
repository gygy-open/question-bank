import type { Component } from 'vue'
import type { Editor } from '@tiptap/vue-3'
import { Bold, Italic, Underline, Superscript, Subscript, RemoveFormatting } from '@lucide/vue'

export interface ToolbarItem {
    /** i18n key，渲染时再翻译 */
    labelKey: string
    icon: Component
    action: () => void
    isActive?: () => boolean
    disabled?: () => boolean
}

/** 行内标记按钮（选中才有意义），工具栏与气泡菜单共用。 */
export function getInlineFormatItems(editor: Editor): ToolbarItem[] {
    return [
        {
            labelKey: 'richEditor.format.bold',
            icon: Bold,
            action: () => editor.chain().focus().toggleBold().run(),
            isActive: () => editor.isActive('bold'),
        },
        {
            labelKey: 'richEditor.format.italic',
            icon: Italic,
            action: () => editor.chain().focus().toggleItalic().run(),
            isActive: () => editor.isActive('italic'),
        },
        {
            labelKey: 'richEditor.format.underline',
            icon: Underline,
            action: () => editor.chain().focus().toggleUnderline().run(),
            isActive: () => editor.isActive('underline'),
        },
        {
            labelKey: 'richEditor.format.superscript',
            icon: Superscript,
            action: () => editor.chain().focus().toggleSuperscript().run(),
            isActive: () => editor.isActive('superscript'),
        },
        {
            labelKey: 'richEditor.format.subscript',
            icon: Subscript,
            action: () => editor.chain().focus().toggleSubscript().run(),
            isActive: () => editor.isActive('subscript'),
        },
        {
            labelKey: 'richEditor.format.clear',
            icon: RemoveFormatting,
            action: () => editor.chain().focus().unsetAllMarks().clearNodes().run(),
        },
    ]
}
