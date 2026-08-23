import type { Component } from 'vue'
import type { Editor, Range } from '@tiptap/core'
import { Extension } from '@tiptap/core'
import { VueRenderer } from '@tiptap/vue-3'
import Suggestion from '@tiptap/suggestion'
import type { SuggestionKeyDownProps, SuggestionProps } from '@tiptap/suggestion'
import {
    Type,
    List,
    ListOrdered,
    ImageIcon,
    Sigma,
    SquareSigma,
} from '@lucide/vue'
import SlashCommandList from './SlashCommandList.vue'

export interface SlashCommandOptions {
    /** Called when the "image" item is picked, so the host can open a file picker. */
    onImageSelect?: () => void
    /** Called when a math item is picked, so the host can open the math dialog. */
    onInsertMath?: (isBlock: boolean) => void
}

export interface SlashCommandItem {
    title: string
    icon: Component
    aliases?: string[]
    command: (opts: { editor: Editor; range: Range; options: SlashCommandOptions }) => void
}

const ITEMS: SlashCommandItem[] = [
    {
        title: '正文',
        icon: Type,
        aliases: ['paragraph', 'text', 'zhengwen', 'p'],
        command: ({ editor, range }) => {
            editor.chain().focus().deleteRange(range).setParagraph().run()
        },
    },
    {
        title: '无序列表',
        icon: List,
        aliases: ['bullet', 'ul', 'list', 'liebiao'],
        command: ({ editor, range }) => {
            editor.chain().focus().deleteRange(range).toggleBulletList().run()
        },
    },
    {
        title: '有序列表',
        icon: ListOrdered,
        aliases: ['ordered', 'ol', 'number', 'liebiao'],
        command: ({ editor, range }) => {
            editor.chain().focus().deleteRange(range).toggleOrderedList().run()
        },
    },
    {
        title: '图片',
        icon: ImageIcon,
        aliases: ['image', 'img', 'picture', 'tupian'],
        command: ({ editor, range, options }) => {
            editor.chain().focus().deleteRange(range).run()
            options.onImageSelect?.()
        },
    },
    {
        title: '行内公式',
        icon: Sigma,
        aliases: ['inline math', 'formula', 'gongshi', 'latex'],
        command: ({ editor, range, options }) => {
            editor.chain().focus().deleteRange(range).run()
            options.onInsertMath?.(false)
        },
    },
    {
        title: '块公式',
        icon: SquareSigma,
        aliases: ['block math', 'formula', 'gongshi', 'latex'],
        command: ({ editor, range, options }) => {
            editor.chain().focus().deleteRange(range).run()
            options.onInsertMath?.(true)
        },
    },
]

function getSuggestionItems(query: string): SlashCommandItem[] {
    const q = query.trim().toLowerCase()
    if (!q) {
        return ITEMS
    }
    return ITEMS.filter((item) => {
        if (item.title.toLowerCase().includes(q)) {
            return true
        }
        return item.aliases?.some((alias) => alias.includes(q)) ?? false
    })
}

function createRenderer() {
    let component: VueRenderer | null = null
    let unmount: (() => void) | null = null

    return {
        onStart: (props: SuggestionProps<SlashCommandItem>) => {
            component = new VueRenderer(SlashCommandList, {
                props,
                editor: props.editor,
            })

            if (!props.clientRect) {
                return
            }

            unmount = props.mount(component.element as HTMLElement)
        },
        onUpdate: (props: SuggestionProps<SlashCommandItem>) => {
            component?.updateProps(props)
        },
        onKeyDown: (props: SuggestionKeyDownProps): boolean => {
            if (props.event.key === 'Escape') {
                return false
            }
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

export const SlashCommand = Extension.create<SlashCommandOptions>({
    name: 'slashCommand',

    addOptions() {
        return {
            onImageSelect: undefined,
        }
    },

    addProseMirrorPlugins() {
        const options = this.options

        return [
            Suggestion<SlashCommandItem>({
                editor: this.editor,
                char: '/',
                allowSpaces: false,
                startOfLine: false,
                items: ({ query }) => getSuggestionItems(query),
                command: ({ editor, range, props }) => {
                    props.command({ editor, range, options })
                },
                render: createRenderer,
            }),
        ]
    },
})
