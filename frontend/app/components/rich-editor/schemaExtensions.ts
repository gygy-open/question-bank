import StarterKit from '@tiptap/starter-kit'
import Image from '@tiptap/extension-image'
import Superscript from '@tiptap/extension-superscript'
import Subscript from '@tiptap/extension-subscript'
import TextAlign from '@tiptap/extension-text-align'
import { InlineMath, BlockMath } from '@tiptap/extension-mathematics'
import type { NodeViewRenderer } from '@tiptap/core'

export interface SchemaExtensionOptions {
    /** 公式节点的自定义 nodeView（编辑器传入 MathLive 就地编辑；只读渲染不传，走库自带 KaTeX 渲染）。 */
    mathNodeView?: NodeViewRenderer
}

/** 决定 schema 的扩展集合，编辑与只读渲染必须保持一致，否则内容会跑版或丢失。 */
export function getSchemaExtensions(options: SchemaExtensionOptions = {}) {
    const inlineMath = options.mathNodeView
        ? InlineMath.extend({ addNodeView: () => options.mathNodeView! })
        : InlineMath
    const blockMath = options.mathNodeView
        ? BlockMath.extend({ addNodeView: () => options.mathNodeView! })
        : BlockMath

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
        inlineMath.configure({ katexOptions: { throwOnError: false } }),
        blockMath.configure({ katexOptions: { throwOnError: false, displayMode: true } }),
    ]
}
