// 分页符：atom 块节点，可拖拽、可选中；不含内容。
import { Node, mergeAttributes } from '@tiptap/core'

export const PageBreak = Node.create({
  name: 'pageBreak',
  group: 'block',
  atom: true,
  selectable: true,
  draggable: true,

  parseHTML() {
    return [{ tag: 'div[data-type="page-break"]' }]
  },

  renderHTML({ HTMLAttributes }) {
    return [
      'div',
      mergeAttributes(HTMLAttributes, {
        'data-type': 'page-break',
        class: 'composition-page-break',
        role: 'separator',
        'aria-label': '分页符',
      }),
    ]
  },
})
