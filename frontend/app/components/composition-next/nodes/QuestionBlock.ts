// 题目块：atom 节点。内容是插入时冻结的快照（不进 PM schema 内部编辑），
// 通过 attrs 承载 question_id / revision / 快照 / props，NodeView 只读渲染并保留同步语义。
import { Node, mergeAttributes } from '@tiptap/core'
import { VueNodeViewRenderer } from '@tiptap/vue-3'
import QuestionBlockView from './QuestionBlockView.vue'

export const QuestionBlock = Node.create({
  name: 'question',
  group: 'block',
  atom: true,
  selectable: true,
  draggable: true,

  addAttributes() {
    return {
      questionId: { default: null },
      questionRevision: { default: null },
      // QuestionContentSnapshot；atom 节点里以对象形态存放，走 getJSON 往返（不依赖 HTML 序列化）。
      snapshot: { default: null },
      // QuestionProps（题号/分值/字段显隐/选项排版）。
      props: { default: null },
    }
  },

  parseHTML() {
    return [{ tag: 'div[data-type="question"]' }]
  },

  renderHTML({ HTMLAttributes }) {
    return ['div', mergeAttributes(HTMLAttributes, { 'data-type': 'question' })]
  },

  addNodeView() {
    return VueNodeViewRenderer(QuestionBlockView)
  },
})
