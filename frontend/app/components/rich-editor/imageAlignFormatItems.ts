import type { Editor } from '@tiptap/vue-3'
import { AlignLeft, AlignCenter, AlignRight } from '@lucide/vue'
import type { ToolbarItem } from './inlineFormatItems'
import type { ImageAlign } from './schemaExtensions'

/** 图片对齐按钮（气泡菜单选中图片时展示）；'left' 落回默认值 null，不占用额外属性。 */
export function getImageAlignFormatItems(editor: Editor): ToolbarItem[] {
    const items: { label: string; icon: typeof AlignLeft; align: ImageAlign }[] = [
        { label: '图片左对齐', icon: AlignLeft, align: 'left' },
        { label: '图片居中', icon: AlignCenter, align: 'center' },
        { label: '图片右对齐', icon: AlignRight, align: 'right' },
    ]

    return items.map(({ label, icon, align }) => ({
        label,
        icon,
        action: () =>
            editor
                .chain()
                .focus()
                .updateAttributes('image', { align: align === 'left' ? null : align })
                .run(),
        isActive: () => {
            const current = editor.getAttributes('image').align ?? 'left'
            return current === align
        },
    }))
}
