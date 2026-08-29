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
    /** 编辑器启用图片四角等比缩放；静态渲染不创建 nodeView。 */
    imageResizable?: boolean
}

declare module '@tiptap/core' {
    interface Commands<ReturnType> {
        blank: {
            /** 在当前光标处插入一个填空节点；不传 id 时自动生成。 */
            insertBlank: (blankId?: string) => ReturnType
            /** 设置指定位置填空节点的显示宽度（em）。 */
            setBlankWidth: (pos: number, widthEm: number) => ReturnType
            /** 删除指定位置的填空节点。 */
            removeBlank: (pos: number) => ReturnType
        }
    }
}

/** 填空节点可调整宽度（em）的合法区间与默认值，与后端 question_content 对齐。 */
export const BLANK_WIDTH_MIN_EM = 2
export const BLANK_WIDTH_MAX_EM = 30
export const BLANK_WIDTH_DEFAULT_EM = 4

export type ImageAlign = 'left' | 'center' | 'right'

function syncImageAlign(container: HTMLElement, align: unknown) {
    container.style.justifyContent = align === 'center' ? 'center' : align === 'right' ? 'flex-end' : 'flex-start'
}

/**
 * 支持四角缩放 + 左/中/右对齐的图片节点。
 * 对齐通过设置外层 flex 容器（resize nodeView 的 dom）的 justify-content 实现——
 * wrapper 按图片内容宽度撑开，margin:auto 加在 img/wrapper 上都不生效。
 * 只读渲染（无 nodeView）走 renderHTML 的 data-align + CSS。
 */
export const ResizableImage = Image.extend({
    addAttributes() {
        return {
            ...this.parent?.(),
            align: {
                default: null,
                parseHTML: (el: HTMLElement) => el.getAttribute('data-align'),
                renderHTML: (attrs: { align?: ImageAlign | null }) =>
                    attrs.align ? { 'data-align': attrs.align } : {},
            },
        }
    },

    addNodeView() {
        const base = this.parent?.()
        if (!base) {
            return base
        }
        return (props) => {
            const nodeView = base(props)
            const container = nodeView.dom as HTMLElement
            syncImageAlign(container, props.node.attrs.align)
            const baseUpdate = nodeView.update?.bind(nodeView)
            nodeView.update = (node, decorations, innerDecorations) => {
                const result = baseUpdate ? baseUpdate(node, decorations, innerDecorations) : true
                syncImageAlign(container, node.attrs.align)
                return result
            }
            return nodeView
        }
    },
})

/** 把任意输入规整为 [2, 30] 的整数 em；非法/缺省回退默认宽度。 */
export function clampBlankWidthEm(value: unknown): number {
    const n = typeof value === 'number' ? value : Number(value)
    if (!Number.isFinite(n)) {
        return BLANK_WIDTH_DEFAULT_EM
    }
    return Math.min(BLANK_WIDTH_MAX_EM, Math.max(BLANK_WIDTH_MIN_EM, Math.round(n)))
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
            widthEm: {
                default: BLANK_WIDTH_DEFAULT_EM,
                parseHTML: (el) => {
                    const raw = el.getAttribute('data-width-em')
                    return raw == null ? BLANK_WIDTH_DEFAULT_EM : clampBlankWidthEm(raw)
                },
                renderHTML: (attrs) => {
                    const width = clampBlankWidthEm(attrs.widthEm)
                    return { 'data-width-em': String(width), style: `width:${width}em` }
                },
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
            setBlankWidth:
                (pos: number, widthEm: number) =>
                ({ tr, dispatch }) => {
                    const node = tr.doc.nodeAt(pos)
                    if (!node || node.type.name !== this.name) {
                        return false
                    }
                    if (dispatch) {
                        tr.setNodeMarkup(pos, undefined, {
                            ...node.attrs,
                            widthEm: clampBlankWidthEm(widthEm),
                        })
                    }
                    return true
                },
            removeBlank:
                (pos: number) =>
                ({ tr, dispatch }) => {
                    const node = tr.doc.nodeAt(pos)
                    if (!node || node.type.name !== this.name) {
                        return false
                    }
                    if (dispatch) {
                        tr.delete(pos, pos + node.nodeSize)
                    }
                    return true
                },
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
        ResizableImage.configure({
            inline: false,
            resize: options.imageResizable
                ? {
                    enabled: true,
                    directions: ['top-left', 'top-right', 'bottom-left', 'bottom-right'],
                    minWidth: 32,
                    minHeight: 32,
                    alwaysPreserveAspectRatio: true,
                }
                : false,
        }),
        Table.configure({ resizable: false }),
        TableRow,
        TableHeader,
        TableCell,
        inlineMath.configure({ katexOptions: { throwOnError: false } }),
        blockMath.configure({ katexOptions: { throwOnError: false, displayMode: true } }),
        blank,
    ]
}
