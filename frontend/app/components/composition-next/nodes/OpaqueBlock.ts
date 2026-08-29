// 不透明块：暂未原生化的节点（question_details 模块）在单文档里的无损占位。
// attrs.node 完整承载原 EditorNode（含 children），保证 PM ⇄ 行 往返不丢数据；
// 编辑能力将在 Phase 2/4 以嵌套子编辑器实现。
import { Node, mergeAttributes } from '@tiptap/core'
import { VueNodeViewRenderer } from '@tiptap/vue-3'
import OpaqueBlockView from './OpaqueBlockView.vue'

export const OpaqueBlock = Node.create({
  name: 'opaqueBlock',
  group: 'block',
  atom: true,
  selectable: true,
  draggable: true,

  addAttributes() {
    return {
      // 序列化后的 EditorNode（不含 id，其身份由 uid 承载）。
      node: { default: null },
    }
  },

  parseHTML() {
    return [{ tag: 'div[data-type="opaque-block"]' }]
  },

  renderHTML({ HTMLAttributes }) {
    return ['div', mergeAttributes(HTMLAttributes, { 'data-type': 'opaque-block' })]
  },

  addNodeView() {
    return VueNodeViewRenderer(OpaqueBlockView)
  },
})
