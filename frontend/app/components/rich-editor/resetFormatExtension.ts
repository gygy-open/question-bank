import { Extension } from '@tiptap/vue-3'

/**
 * 在段落中回车另起一段时，不把当前段的对齐方式和激活的行内标记带到新段落。
 * 仅处理普通段落，列表/公式等节点保持各自默认的回车行为。
 */
export const ResetFormatOnEnter = Extension.create({
    name: 'resetFormatOnEnter',

    addKeyboardShortcuts() {
        return {
            Enter: () => {
                const { editor } = this
                const { $from, empty } = editor.state.selection

                if (!empty || $from.parent.type.name !== 'paragraph') {
                    return false
                }

                return editor
                    .chain()
                    .splitBlock({ keepMarks: false })
                    .updateAttributes('paragraph', { textAlign: null })
                    .run()
            },
        }
    },
})
