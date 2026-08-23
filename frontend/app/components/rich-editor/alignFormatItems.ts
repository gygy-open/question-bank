import type { Editor } from '@tiptap/vue-3'
import { AlignLeft, AlignCenter, AlignRight, AlignJustify } from '@lucide/vue'
import type { ToolbarItem } from './inlineFormatItems'

/** 段落对齐方式按钮，工具栏与气泡菜单共用。 */
export function getAlignFormatItems(editor: Editor): ToolbarItem[] {
    return [
        {
            label: '左对齐',
            icon: AlignLeft,
            action: () => editor.chain().focus().setTextAlign('left').run(),
            isActive: () => editor.isActive({ textAlign: 'left' }),
        },
        {
            label: '居中',
            icon: AlignCenter,
            action: () => editor.chain().focus().setTextAlign('center').run(),
            isActive: () => editor.isActive({ textAlign: 'center' }),
        },
        {
            label: '右对齐',
            icon: AlignRight,
            action: () => editor.chain().focus().setTextAlign('right').run(),
            isActive: () => editor.isActive({ textAlign: 'right' }),
        },
        {
            label: '两端对齐',
            icon: AlignJustify,
            action: () => editor.chain().focus().setTextAlign('justify').run(),
            isActive: () => editor.isActive({ textAlign: 'justify' }),
        },
    ]
}
