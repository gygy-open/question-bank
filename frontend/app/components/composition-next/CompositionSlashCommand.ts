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
  FileQuestion, Files, ListChecks, PencilLine,
} from '@lucide/vue'
import SlashCommandList from '@/components/rich-editor/SlashCommandList.vue'
import { resolveAnswerSpacePropsOrFallback } from '@/lib/answerSpaceRules'
import { translate } from '@/lib/locale'

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

// 定义里只存 i18n key，查询时再翻译，保证切换语言后菜单文案随之更新。
interface CompositionSlashItemDef extends Omit<CompositionSlashItem, 'title' | 'group'> {
  titleKey: string
  groupKey: string
}

const ITEMS: CompositionSlashItemDef[] = [
  {
    titleKey: 'compositionEditor.slash.items.paragraph', icon: Type, groupKey: 'compositionEditor.slash.groups.basic', aliases: ['paragraph', 'text', 'zhengwen', 'p'],
    command: ({ editor, range }) => editor.chain().focus().deleteRange(range).setParagraph().run(),
  },
  {
    titleKey: 'compositionEditor.slash.items.heading1', icon: Heading1, groupKey: 'compositionEditor.slash.groups.basic', aliases: ['h1', 'heading', 'biaoti'],
    command: ({ editor, range }) => editor.chain().focus().deleteRange(range).setHeading({ level: 1 }).run(),
  },
  {
    titleKey: 'compositionEditor.slash.items.heading2', icon: Heading2, groupKey: 'compositionEditor.slash.groups.basic', aliases: ['h2', 'heading', 'biaoti'],
    command: ({ editor, range }) => editor.chain().focus().deleteRange(range).setHeading({ level: 2 }).run(),
  },
  {
    titleKey: 'compositionEditor.slash.items.heading3', icon: Heading3, groupKey: 'compositionEditor.slash.groups.basic', aliases: ['h3', 'heading', 'biaoti'],
    command: ({ editor, range }) => editor.chain().focus().deleteRange(range).setHeading({ level: 3 }).run(),
  },
  {
    titleKey: 'compositionEditor.slash.items.bulletList', icon: List, groupKey: 'compositionEditor.slash.groups.basic', aliases: ['bullet', 'ul', 'list', 'liebiao'],
    command: ({ editor, range }) => editor.chain().focus().deleteRange(range).toggleBulletList().run(),
  },
  {
    titleKey: 'compositionEditor.slash.items.orderedList', icon: ListOrdered, groupKey: 'compositionEditor.slash.groups.basic', aliases: ['ordered', 'ol', 'number', 'liebiao'],
    command: ({ editor, range }) => editor.chain().focus().deleteRange(range).toggleOrderedList().run(),
  },
  {
    titleKey: 'compositionEditor.slash.items.quote', icon: Quote, groupKey: 'compositionEditor.slash.groups.block', aliases: ['quote', 'blockquote', 'yinyong'],
    command: ({ editor, range }) => editor.chain().focus().deleteRange(range).toggleBlockquote().run(),
  },
  {
    titleKey: 'compositionEditor.slash.items.codeBlock', icon: Code, groupKey: 'compositionEditor.slash.groups.block', aliases: ['code', 'codeblock', 'daima'],
    command: ({ editor, range }) => editor.chain().focus().deleteRange(range).toggleCodeBlock().run(),
  },
  {
    titleKey: 'compositionEditor.slash.items.divider', icon: Minus, groupKey: 'compositionEditor.slash.groups.block', aliases: ['hr', 'divider', 'rule', 'fengexian'],
    command: ({ editor, range }) => editor.chain().focus().deleteRange(range).setHorizontalRule().run(),
  },
  {
    titleKey: 'compositionEditor.slash.items.table', icon: TableIcon, groupKey: 'compositionEditor.slash.groups.block', aliases: ['table', 'biaoge'],
    command: ({ editor, range }) =>
      editor.chain().focus().deleteRange(range).insertTable({ rows: 2, cols: 2, withHeaderRow: true }).run(),
  },
  {
    titleKey: 'compositionEditor.slash.items.pageBreak', icon: SeparatorHorizontal, groupKey: 'compositionEditor.slash.groups.block', aliases: ['pagebreak', 'page', 'fenye'],
    command: ({ editor, range }) =>
      editor.chain().focus().deleteRange(range).insertContent({ type: 'pageBreak' }).run(),
  },
  {
    titleKey: 'compositionEditor.slash.items.answerSpace', icon: PencilLine, groupKey: 'compositionEditor.slash.groups.block',
    aliases: ['answer', 'space', 'zuoda', 'kongbai', 'liubai', 'zuodakongjian'],
    command: ({ editor, range }) => {
      // 根层插入无题目上下文，取与后端一致的兜底规则。
      const { lines, style } = resolveAnswerSpacePropsOrFallback(null, null)
      return editor.chain().focus().deleteRange(range)
        .insertContent({ type: 'answerSpace', attrs: { lines, style } }).run()
    },
  },
  {
    titleKey: 'compositionEditor.slash.items.question', icon: FileQuestion, groupKey: 'compositionEditor.slash.groups.composition', aliases: ['question', 'timu', 'q'],
    command: ({ editor, range, options }) => {
      editor.chain().focus().deleteRange(range).run()
      options.onInsertQuestion?.()
    },
  },
  {
    titleKey: 'compositionEditor.slash.items.composition', icon: Files, groupKey: 'compositionEditor.slash.groups.composition', aliases: ['composition', 'gaojian', 'insert'],
    command: ({ editor, range, options }) => {
      editor.chain().focus().deleteRange(range).run()
      options.onInsertComposition?.()
    },
  },
  {
    titleKey: 'compositionEditor.slash.items.answerModule', icon: ListChecks, groupKey: 'compositionEditor.slash.groups.composition', aliases: ['module', 'answer', 'canhkao', 'daan', 'mokuai'],
    command: ({ editor, range, options }) => {
      editor.chain().focus().deleteRange(range).run()
      options.onInsertModule?.()
    },
  },
  {
    titleKey: 'compositionEditor.slash.items.image', icon: ImageIcon, groupKey: 'compositionEditor.slash.groups.insert', aliases: ['image', 'img', 'picture', 'tupian'],
    command: ({ editor, range, options }) => {
      editor.chain().focus().deleteRange(range).run()
      options.onImageSelect?.()
    },
  },
  {
    titleKey: 'compositionEditor.slash.items.inlineMath', icon: Sigma, groupKey: 'compositionEditor.slash.groups.insert', aliases: ['inline math', 'formula', 'gongshi', 'latex'],
    command: ({ editor, range, options }) => {
      editor.chain().focus().deleteRange(range).run()
      options.onInsertMath?.(false)
    },
  },
  {
    titleKey: 'compositionEditor.slash.items.blockMath', icon: SquareSigma, groupKey: 'compositionEditor.slash.groups.insert', aliases: ['block math', 'formula', 'gongshi', 'latex'],
    command: ({ editor, range, options }) => {
      editor.chain().focus().deleteRange(range).run()
      options.onInsertMath?.(true)
    },
  },
]

function getSuggestionItems(query: string): CompositionSlashItem[] {
  const items = ITEMS.map(({ titleKey, groupKey, ...rest }) => ({
    ...rest,
    title: translate(titleKey),
    group: translate(groupKey),
  }))
  const q = query.trim().toLowerCase()
  if (!q) return items
  return items.filter(
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
