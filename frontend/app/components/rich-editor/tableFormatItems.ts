import type { Editor } from '@tiptap/vue-3'
import {
    ArrowUpToLine,
    ArrowDownToLine,
    ArrowLeftToLine,
    ArrowRightToLine,
    Trash2,
    TableCellsMerge,
    TableCellsSplit,
    PanelTopDashed,
    PanelLeftDashed,
} from '@lucide/vue'
import type { ToolbarItem } from './inlineFormatItems'

/** 表格内浮动工具栏按钮：按行/列/合并拆分/表头与删除分组，供气泡菜单按组渲染分隔线。 */
export function getTableFormatItemGroups(editor: Editor): ToolbarItem[][] {
    return [
        [
            {
                label: '上方插入行',
                icon: ArrowUpToLine,
                action: () => editor.chain().focus().addRowBefore().run(),
                disabled: () => !editor.can().addRowBefore(),
            },
            {
                label: '下方插入行',
                icon: ArrowDownToLine,
                action: () => editor.chain().focus().addRowAfter().run(),
                disabled: () => !editor.can().addRowAfter(),
            },
            {
                label: '删除行',
                icon: Trash2,
                action: () => editor.chain().focus().deleteRow().run(),
                disabled: () => !editor.can().deleteRow(),
            },
        ],
        [
            {
                label: '左侧插入列',
                icon: ArrowLeftToLine,
                action: () => editor.chain().focus().addColumnBefore().run(),
                disabled: () => !editor.can().addColumnBefore(),
            },
            {
                label: '右侧插入列',
                icon: ArrowRightToLine,
                action: () => editor.chain().focus().addColumnAfter().run(),
                disabled: () => !editor.can().addColumnAfter(),
            },
            {
                label: '删除列',
                icon: Trash2,
                action: () => editor.chain().focus().deleteColumn().run(),
                disabled: () => !editor.can().deleteColumn(),
            },
        ],
        [
            {
                label: '合并单元格',
                icon: TableCellsMerge,
                action: () => editor.chain().focus().mergeCells().run(),
                disabled: () => !editor.can().mergeCells(),
            },
            {
                label: '拆分单元格',
                icon: TableCellsSplit,
                action: () => editor.chain().focus().splitCell().run(),
                disabled: () => !editor.can().splitCell(),
            },
        ],
        [
            {
                label: '切换表头行',
                icon: PanelTopDashed,
                action: () => editor.chain().focus().toggleHeaderRow().run(),
            },
            {
                label: '切换表头列',
                icon: PanelLeftDashed,
                action: () => editor.chain().focus().toggleHeaderColumn().run(),
            },
            {
                label: '删除表格',
                icon: Trash2,
                action: () => editor.chain().focus().deleteTable().run(),
            },
        ],
    ]
}
