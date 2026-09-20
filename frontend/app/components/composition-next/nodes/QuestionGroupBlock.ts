import { Node, mergeAttributes } from '@tiptap/core'
import { VueNodeViewRenderer } from '@tiptap/vue-3'
import QuestionGroupBlockView from './QuestionGroupBlockView.vue'

/** 原生题组 atom：材料与成员结构冻结，完整 children 通过 attrs JSON 往返。 */
export const QuestionGroupBlock = Node.create({
  name: 'questionGroup',
  group: 'block',
  atom: true,
  selectable: true,
  draggable: true,

  addAttributes() {
    return {
      questionGroupId: { default: null },
      questionGroupRevision: { default: null },
      stimulusId: { default: null },
      stimulusRevision: { default: null },
      stimulus: { default: null },
      children: { default: [] },
    }
  },

  parseHTML() {
    return [{ tag: 'div[data-type="question-group"]' }]
  },

  renderHTML({ HTMLAttributes }) {
    return ['div', mergeAttributes(HTMLAttributes, { 'data-type': 'question-group' })]
  },

  addNodeView() {
    return VueNodeViewRenderer(QuestionGroupBlockView)
  },
})