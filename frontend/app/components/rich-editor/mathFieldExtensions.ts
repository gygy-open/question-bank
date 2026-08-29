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

// 插入公式与节点挂载之间的确定性握手：插入时打标记，新节点挂载时消费它自动进入行内编辑，
// 借此区分「刚插入的空公式」与「页面加载的持久空节点」（后者不应抢焦点）。
let pendingAutofocusAt = 0
export function requestMathAutofocus(): void {
    pendingAutofocusAt = Date.now()
}
export function consumeMathAutofocus(): boolean {
    const recent = Date.now() - pendingAutofocusAt < 800
    pendingAutofocusAt = 0
    return recent
}
