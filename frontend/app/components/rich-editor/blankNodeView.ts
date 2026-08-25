import type { NodeViewRenderer } from '@tiptap/core'
import { VueNodeViewRenderer } from '@tiptap/vue-3'
import BlankNode from './BlankNode.vue'

/** 填空节点的 nodeView；点击时打开外部浮层调整长度。仅编辑器使用，只读渲染走 renderHTML。 */
export function createBlankNodeView(): NodeViewRenderer {
    return VueNodeViewRenderer(BlankNode)
}
