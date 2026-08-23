import type { NodeViewRenderer } from '@tiptap/core'
import { VueNodeViewRenderer } from '@tiptap/vue-3'
import MathFieldNode from './MathFieldNode.vue'

/** MathLive 就地编辑的 nodeView；stopEvent/ignoreMutation 让 ProseMirror 不干预 web component 自身编辑。 */
export function createMathNodeView(): NodeViewRenderer {
    return VueNodeViewRenderer(MathFieldNode, {
        stopEvent: () => true,
        ignoreMutation: () => true,
    })
}
