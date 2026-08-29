// 组稿单文档专用斜杠命令：在 rich-editor 的斜杠基础上补齐顶层块（标题/引用/代码/分隔线/
// 表格/分页），并复用 SlashCommandList 渲染器与 SlashCommandItem 形状。
import type { Component } from 'vue'
import type { Editor, Range } from '@tiptap/core'
import { Extension } from '@tiptap/core'
import { VueRenderer } from '@tiptap/vue-3'
import Suggestion from '@tiptap/suggestion'
import type { SuggestionKeyDownProps, SuggestionProps } from '@tiptap/suggestion'
import {
  Type, Heading1, Heading2, Heading3, List, ListOrdered, Quote, Code, Minus,
  Table as TableIcon, Sigma, SquareSigma, ImageIcon, SeparatorHorizontal,
  FileQuestion, Files, ListChecks,
} from '@lucide/vue'
import SlashCommandList from '@/components/rich-editor/SlashCommandList.vue'

export interface CompositionSlashOptions {
  onImageSelect?: () => void
  onInsertMath?: (isBlock: boolean) => void
  onInsertQuestion?: () => void
  onInsertComposition?: () => void
  onInsertModule?: () => void
}

// 与 rich-editor SlashCommandItem 同形，但 command 的 options 用组稿版。
interface CompositionSlashItem {
  title: string
  icon: Component
  aliases?: string[]
  group?: string
  command: (opts: { editor: Editor; range: Range; options: CompositionSlashOptions }) => void
}

const ITEMS: CompositionSlashItem[] = [
  {
    title: '正文', icon: Type, group: '基础', aliases: ['paragraph', 'text', 'zhengwen', 'p'],
    command: ({ editor, range }) => editor.chain().focus().deleteRange(range).setParagraph().run(),
  },
  {
    title: '标题 1', icon: Heading1, group: '基础', aliases: ['h1', 'heading', 'biaoti'],
    command: ({ editor, range }) => editor.chain().focus().deleteRange(range).setHeading({ level: 1 }).run(),
  },
  {
    title: '标题 2', icon: Heading2, group: '基础', aliases: ['h2', 'heading', 'biaoti'],
    command: ({ editor, range }) => editor.chain().focus().deleteRange(range).setHeading({ level: 2 }).run(),
  },
  {
    title: '标题 3', icon: Heading3, group: '基础', aliases: ['h3', 'heading', 'biaoti'],
    command: ({ editor, range }) => editor.chain().focus().deleteRange(range).setHeading({ level: 3 }).run(),
  },
  {
    title: '无序列表', icon: List, group: '基础', aliases: ['bullet', 'ul', 'list', 'liebiao'],
    command: ({ editor, range }) => editor.chain().focus().deleteRange(range).toggleBulletList().run(),
  },
  {
    title: '有序列表', icon: ListOrdered, group: '基础', aliases: ['ordered', 'ol', 'number', 'liebiao'],
    command: ({ editor, range }) => editor.chain().focus().deleteRange(range).toggleOrderedList().run(),
  },
  {
    title: '引用', icon: Quote, group: '块', aliases: ['quote', 'blockquote', 'yinyong'],
    command: ({ editor, range }) => editor.chain().focus().deleteRange(range).toggleBlockquote().run(),
  },
  {
    title: '代码块', icon: Code, group: '块', aliases: ['code', 'codeblock', 'daima'],
    command: ({ editor, range }) => editor.chain().focus().deleteRange(range).toggleCodeBlock().run(),
  },
  {
    title: '分隔线', icon: Minus, group: '块', aliases: ['hr', 'divider', 'rule', 'fengexian'],
    command: ({ editor, range }) => editor.chain().focus().deleteRange(range).setHorizontalRule().run(),
  },
  {
    title: '表格', icon: TableIcon, group: '块', aliases: ['table', 'biaoge'],
    command: ({ editor, range }) =>
      editor.chain().focus().deleteRange(range).insertTable({ rows: 2, cols: 2, withHeaderRow: true }).run(),
  },
  {
    title: '分页符', icon: SeparatorHorizontal, group: '块', aliases: ['pagebreak', 'page', 'fenye'],
    command: ({ editor, range }) =>
      editor.chain().focus().deleteRange(range).insertContent({ type: 'pageBreak' }).run(),
  },
  {
    title: '题目', icon: FileQuestion, group: '组稿', aliases: ['question', 'timu', 'q'],
    command: ({ editor, range, options }) => {
      editor.chain().focus().deleteRange(range).run()
      options.onInsertQuestion?.()
    },
  },
  {
    title: '插入稿件', icon: Files, group: '组稿', aliases: ['composition', 'gaojian', 'insert'],
    command: ({ editor, range, options }) => {
      editor.chain().focus().deleteRange(range).run()
      options.onInsertComposition?.()
    },
  },
  {
    title: '参考答案模块', icon: ListChecks, group: '组稿', aliases: ['module', 'answer', 'canhkao', 'daan', 'mokuai'],
    command: ({ editor, range, options }) => {
      editor.chain().focus().deleteRange(range).run()
      options.onInsertModule?.()
    },
  },
  {
    title: '图片', icon: ImageIcon, group: '插入', aliases: ['image', 'img', 'picture', 'tupian'],
    command: ({ editor, range, options }) => {
      editor.chain().focus().deleteRange(range).run()
      options.onImageSelect?.()
    },
  },
  {
    title: '行内公式', icon: Sigma, group: '插入', aliases: ['inline math', 'formula', 'gongshi', 'latex'],
    command: ({ editor, range, options }) => {
      editor.chain().focus().deleteRange(range).run()
      options.onInsertMath?.(false)
    },
  },
  {
    title: '块公式', icon: SquareSigma, group: '插入', aliases: ['block math', 'formula', 'gongshi', 'latex'],
    command: ({ editor, range, options }) => {
      editor.chain().focus().deleteRange(range).run()
      options.onInsertMath?.(true)
    },
  },
]

function getSuggestionItems(query: string): CompositionSlashItem[] {
  const q = query.trim().toLowerCase()
  if (!q) return ITEMS
  return ITEMS.filter(
    (item) =>
      item.title.toLowerCase().includes(q) || (item.aliases?.some((a) => a.includes(q)) ?? false),
  )
}

function createRenderer() {
  let component: VueRenderer | null = null
  let unmount: (() => void) | null = null
  return {
    onStart: (props: SuggestionProps<CompositionSlashItem>) => {
      component = new VueRenderer(SlashCommandList, { props, editor: props.editor })
      if (!props.clientRect) return
      unmount = props.mount(component.element as HTMLElement)
    },
    onUpdate: (props: SuggestionProps<CompositionSlashItem>) => component?.updateProps(props),
    onKeyDown: (props: SuggestionKeyDownProps): boolean => {
      if (props.event.key === 'Escape') return false
      return component?.ref?.onKeyDown(props) ?? false
    },
    onExit: () => {
      unmount?.()
      component?.destroy()
      component = null
      unmount = null
    },
  }
}

export const CompositionSlashCommand = Extension.create<CompositionSlashOptions>({
  name: 'compositionSlashCommand',

  addOptions() {
    return { onImageSelect: undefined, onInsertMath: undefined }
  },

  addProseMirrorPlugins() {
    const options = this.options
    return [
      Suggestion<CompositionSlashItem>({
        editor: this.editor,
        char: '/',
        allowSpaces: false,
        startOfLine: false,
        items: ({ query }: { query: string }) => getSuggestionItems(query),
        command: ({ editor, range, props }: { editor: Editor; range: Range; props: CompositionSlashItem }) => {
          props.command({ editor, range, options })
        },
        render: createRenderer,
      }),
    ]
  },
})
