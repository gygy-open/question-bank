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
                labelKey: 'richEditor.table.addRowBefore',
                icon: ArrowUpToLine,
                action: () => editor.chain().focus().addRowBefore().run(),
                disabled: () => !editor.can().addRowBefore(),
            },
            {
                labelKey: 'richEditor.table.addRowAfter',
                icon: ArrowDownToLine,
                action: () => editor.chain().focus().addRowAfter().run(),
                disabled: () => !editor.can().addRowAfter(),
            },
            {
                labelKey: 'richEditor.table.deleteRow',
                icon: Trash2,
                action: () => editor.chain().focus().deleteRow().run(),
                disabled: () => !editor.can().deleteRow(),
            },
        ],
        [
            {
                labelKey: 'richEditor.table.addColumnBefore',
                icon: ArrowLeftToLine,
                action: () => editor.chain().focus().addColumnBefore().run(),
                disabled: () => !editor.can().addColumnBefore(),
            },
            {
                labelKey: 'richEditor.table.addColumnAfter',
                icon: ArrowRightToLine,
                action: () => editor.chain().focus().addColumnAfter().run(),
                disabled: () => !editor.can().addColumnAfter(),
            },
            {
                labelKey: 'richEditor.table.deleteColumn',
                icon: Trash2,
                action: () => editor.chain().focus().deleteColumn().run(),
                disabled: () => !editor.can().deleteColumn(),
            },
        ],
        [
            {
                labelKey: 'richEditor.table.mergeCells',
                icon: TableCellsMerge,
                action: () => editor.chain().focus().mergeCells().run(),
                disabled: () => !editor.can().mergeCells(),
            },
            {
                labelKey: 'richEditor.table.splitCell',
                icon: TableCellsSplit,
                action: () => editor.chain().focus().splitCell().run(),
                disabled: () => !editor.can().splitCell(),
            },
        ],
        [
            {
                labelKey: 'richEditor.table.toggleHeaderRow',
                icon: PanelTopDashed,
                action: () => editor.chain().focus().toggleHeaderRow().run(),
            },
            {
                labelKey: 'richEditor.table.toggleHeaderColumn',
                icon: PanelLeftDashed,
                action: () => editor.chain().focus().toggleHeaderColumn().run(),
            },
            {
                labelKey: 'richEditor.table.deleteTable',
                icon: Trash2,
                action: () => editor.chain().focus().deleteTable().run(),
            },
        ],
    ]
}
