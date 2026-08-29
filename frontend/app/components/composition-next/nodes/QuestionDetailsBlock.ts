// question_details 模块：只读 atom「答案联动展示块」。props(scope/fields) 存 attrs；
// 答案由 NodeView 按 scope + 题目实时派生渲染，不含可编辑内容（authoring 走文档流）。
import { Node, mergeAttributes } from '@tiptap/core'
import { VueNodeViewRenderer } from '@tiptap/vue-3'
import ModuleBlockView from './ModuleBlockView.vue'

export const QuestionDetailsBlock = Node.create({
  name: 'questionDetails',
  group: 'block',
  atom: true,
  selectable: true,
  draggable: true,

  addAttributes() {
    return {
      // QuestionDetailsProps：{ scope, fields }。
      props: { default: null },
    }
  },

  parseHTML() {
    return [{ tag: 'div[data-type="question-details"]' }]
  },

  renderHTML({ HTMLAttributes }) {
    return ['div', mergeAttributes(HTMLAttributes, { 'data-type': 'question-details' })]
  },

  addNodeView() {
    return VueNodeViewRenderer(ModuleBlockView)
  },
})
