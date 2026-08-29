// 组稿「单一 tiptap 文档」实验（Phase 0 Spike）的 schema 装配。
// 与富文本编辑器 getSchemaExtensions 保持内联节点/标记一致，但把 heading/blockquote/
// codeBlock/horizontalRule 这些顶层块打开——它们在组稿文档里是一等公民（每块=一行）。
import StarterKit from '@tiptap/starter-kit'
import Image from '@tiptap/extension-image'
import Superscript from '@tiptap/extension-superscript'
import Subscript from '@tiptap/extension-subscript'
import TextAlign from '@tiptap/extension-text-align'
import { Table, TableRow, TableHeader, TableCell } from '@tiptap/extension-table'
import { InlineMath, BlockMath } from '@tiptap/extension-mathematics'
import type { AnyExtension, NodeViewRenderer } from '@tiptap/core'
import { Blank } from '@/components/rich-editor/schemaExtensions'
import { UniqueId } from './uniqueId'
import { PageBreak } from './nodes/PageBreak'
import { QuestionBlock } from './nodes/QuestionBlock'
import { QuestionDetailsBlock } from './nodes/QuestionDetailsBlock'
import { OpaqueBlock } from './nodes/OpaqueBlock'

/** 携带稳定 uid 的顶层块类型（= composition_node 一行）。 */
export const TOP_LEVEL_TYPES = [
  'paragraph',
  'heading',
  'blockquote',
  'codeBlock',
  'bulletList',
  'orderedList',
  'table',
  'blockMath',
  'horizontalRule',
  'image',
  'pageBreak',
  'question',
  'questionDetails',
  'opaqueBlock',
] as const

export interface CompositionExtensionOptions {
  imageResizable?: boolean
  // 公式/填空的就地编辑 nodeView；只读渲染不传，走库自带 KaTeX / renderHTML 占位。
  mathNodeView?: NodeViewRenderer
  blankNodeView?: NodeViewRenderer
}

/** 组稿文档的扩展集合（编辑与只读渲染需保持一致，否则内容跑版/丢失）。 */
export function getCompositionExtensions(options: CompositionExtensionOptions = {}): AnyExtension[] {
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
      heading: { levels: [1, 2, 3, 4] },
      horizontalRule: {},
      blockquote: {},
      codeBlock: {},
      link: { openOnClick: false },
    }),
    Superscript,
    Subscript,
    TextAlign.configure({ types: ['paragraph', 'heading'] }),
    Image.configure({
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
    PageBreak,
    QuestionBlock,
    QuestionDetailsBlock,
    OpaqueBlock,
    UniqueId.configure({ types: [...TOP_LEVEL_TYPES], attrName: 'uid' }),
  ]
}
