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
    Music,
    Sigma,
    SquareSigma,
} from '@lucide/vue'
import SlashCommandList from './SlashCommandList.vue'
import { DEFAULT_LOCALE, translate } from '@/lib/locale'

export interface SlashCommandOptions {
    /** Called when the "image" item is picked, so the host can open a file picker. */
    onImageSelect?: () => void
    /** Called when the "audio" item is picked, so the host can open the media picker. */
    onAudioSelect?: () => void
    /** Called when a math item is picked, so the host can open the math dialog. */
    onInsertMath?: (isBlock: boolean) => void
}

export interface SlashCommandItem {
    title: string
    icon: Component
    aliases?: string[]
    group?: string
    command: (opts: { editor: Editor; range: Range; options: SlashCommandOptions }) => void
}

// 定义里只存 i18n key，查询时再翻译，保证切换语言后菜单文案随之更新。
interface SlashCommandItemDef extends Omit<SlashCommandItem, 'title'> {
    titleKey: string
}

const ITEMS: SlashCommandItemDef[] = [
    {
        titleKey: 'richEditor.slash.items.paragraph',
        icon: Type,
        aliases: ['paragraph', 'text', 'zhengwen', 'p'],
        command: ({ editor, range }) => {
            editor.chain().focus().deleteRange(range).setParagraph().run()
        },
    },
    {
        titleKey: 'richEditor.slash.items.bulletList',
        icon: List,
        aliases: ['bullet', 'ul', 'list', 'liebiao'],
        command: ({ editor, range }) => {
            editor.chain().focus().deleteRange(range).toggleBulletList().run()
        },
    },
    {
        titleKey: 'richEditor.slash.items.orderedList',
        icon: ListOrdered,
        aliases: ['ordered', 'ol', 'number', 'liebiao'],
        command: ({ editor, range }) => {
            editor.chain().focus().deleteRange(range).toggleOrderedList().run()
        },
    },
    {
        titleKey: 'richEditor.slash.items.image',
        icon: ImageIcon,
        aliases: ['image', 'img', 'picture', 'tupian'],
        command: ({ editor, range, options }) => {
            editor.chain().focus().deleteRange(range).run()
            options.onImageSelect?.()
        },
    },
    {
        titleKey: 'richEditor.slash.items.audio',
        icon: Music,
        aliases: ['audio', 'sound', 'mp3', 'yinpin', 'tingli'],
        command: ({ editor, range, options }) => {
            editor.chain().focus().deleteRange(range).run()
            options.onAudioSelect?.()
        },
    },
    {
        titleKey: 'richEditor.slash.items.inlineMath',
        icon: Sigma,
        aliases: ['inline math', 'formula', 'gongshi', 'latex'],
        command: ({ editor, range, options }) => {
            editor.chain().focus().deleteRange(range).run()
            options.onInsertMath?.(false)
        },
    },
    {
        titleKey: 'richEditor.slash.items.blockMath',
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
    // 额外匹配中文标题，让其他语言界面下也能用中文搜索。
    return ITEMS
        .filter(({ titleKey, aliases }) => !q
            || translate(titleKey).toLowerCase().includes(q)
            || translate(titleKey, undefined, DEFAULT_LOCALE).includes(q)
            || (aliases?.some((alias) => alias.includes(q)) ?? false))
        .map(({ titleKey, ...rest }) => ({ ...rest, title: translate(titleKey) }))
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
            onAudioSelect: undefined,
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
