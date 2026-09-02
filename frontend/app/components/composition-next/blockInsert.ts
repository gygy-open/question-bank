// 顶层 atom 块（题目/答题区/分页符等）被整块选中时的换行插入捷径：
// Enter=下方插入空段落并聚焦，Shift+Enter=上方插入。消除"选中块→方向键→回车"的弯路。
import { Extension } from '@tiptap/core'
import { NodeSelection } from '@tiptap/pm/state'

function insertParagraph(before: boolean) {
  return ({ editor }: { editor: import('@tiptap/core').Editor }) => {
    const sel = editor.state.selection
    if (!(sel instanceof NodeSelection)) return false
    const node = sel.node
    // 仅接管整块选中的 atom 块；非 atom / 行内选区交回默认行为。
    if (!node.type.isAtom || !node.isBlock) return false
    const pos = before ? sel.from : sel.from + node.nodeSize
    return editor
      .chain()
      .insertContentAt(pos, { type: 'paragraph' })
      .setTextSelection(pos + 1)
      .focus()
      .run()
  }
}

export const BlockInsertKeymap = Extension.create({
  name: 'blockInsertKeymap',
  // 高于 StarterKit（HardBreak 等）以便在 atom 选中时优先接管 Shift+Enter。
  priority: 1000,
  addKeyboardShortcuts() {
    return {
      Enter: insertParagraph(false),
      'Shift-Enter': insertParagraph(true),
    }
  },
})
