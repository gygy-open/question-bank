import { Node, mergeAttributes } from '@tiptap/core'
import StarterKit from '@tiptap/starter-kit'
import Image from '@tiptap/extension-image'
import Superscript from '@tiptap/extension-superscript'
import Subscript from '@tiptap/extension-subscript'
import TextAlign from '@tiptap/extension-text-align'
import { Table, TableRow, TableHeader, TableCell } from '@tiptap/extension-table'
import { InlineMath, BlockMath } from '@tiptap/extension-mathematics'
import type { NodeViewRenderer } from '@tiptap/core'
import { generateBlankId } from './richDoc'

export interface SchemaExtensionOptions {
    /** 公式节点的自定义 nodeView（编辑器传入 MathLive 就地编辑；只读渲染不传，走库自带 KaTeX 渲染）。 */
    mathNodeView?: NodeViewRenderer
    /** 填空节点的自定义 nodeView（编辑器可用来交互；只读渲染不传，走 renderHTML 占位）。 */
    blankNodeView?: NodeViewRenderer
}

declare module '@tiptap/core' {
    interface Commands<ReturnType> {
        blank: {
            /** 在当前光标处插入一个填空节点；不传 id 时自动生成。 */
            insertBlank: (blankId?: string) => ReturnType
        }
    }
}

/**
 * 填空节点：inline atom。schema 中恒定存在（编辑与只读渲染共用），
 * 是否可插入/编辑由业务层控制，而非从 schema 中摘除，避免只读场景丢节点。
 * renderHTML 输出带 aria 标签的可访问占位。
 */
export const Blank = Node.create({
    name: 'blank',
    group: 'inline',
    inline: true,
    atom: true,
    selectable: true,

    addAttributes() {
        return {
            blankId: {
                default: null,
                parseHTML: (el) => el.getAttribute('data-blank-id'),
                renderHTML: (attrs) =>
                    attrs.blankId ? { 'data-blank-id': attrs.blankId } : {},
            },
        }
    },

    parseHTML() {
        return [{ tag: 'span[data-type="blank"]' }]
    },

    renderHTML({ HTMLAttributes }) {
        return [
            'span',
            mergeAttributes(HTMLAttributes, {
                'data-type': 'blank',
                class: 'rich-blank',
                role: 'img',
                'aria-label': '填空',
            }),
            '\u2003\u2003\u2003\u2003',
        ]
    },

    addCommands() {
        return {
            insertBlank:
                (blankId?: string) =>
                ({ commands }) =>
                    commands.insertContent({
                        type: this.name,
                        attrs: { blankId: blankId ?? generateBlankId() },
                    }),
        }
    },
})

/** 决定 schema 的扩展集合，编辑与只读渲染必须保持一致，否则内容会跑版或丢失。 */
export function getSchemaExtensions(options: SchemaExtensionOptions = {}) {
    const inlineMath = options.mathNodeView
        ? InlineMath.extend({ addNodeView: () => options.mathNodeView! })
        : InlineMath
    const blockMath = options.mathNodeView
        ? BlockMath.extend({ addNodeView: () => options.mathNodeView! })
        : BlockMath
    const blank = options.blankNodeView
        ? Blank.extend({ addNodeView: () => options.blankNodeView! })
        : Blank

    return [
        StarterKit.configure({
            heading: false,
            blockquote: false,
            codeBlock: false,
            code: false,
            strike: false,
            horizontalRule: false,
            link: { openOnClick: false },
        }),
        Superscript,
        Subscript,
        TextAlign.configure({ types: ['paragraph'] }),
        Image.configure({ inline: false }),
        Table.configure({ resizable: false }),
        TableRow,
        TableHeader,
        TableCell,
        inlineMath.configure({ katexOptions: { throwOnError: false } }),
        blockMath.configure({ katexOptions: { throwOnError: false, displayMode: true } }),
        blank,
    ]
}
