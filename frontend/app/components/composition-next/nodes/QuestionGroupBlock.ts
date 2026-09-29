import { Node, mergeAttributes } from '@tiptap/core'
import { VueNodeViewRenderer } from '@tiptap/vue-3'
import QuestionGroupBlockView from './QuestionGroupBlockView.vue'

/** 材料题 atom：材料冻结，所选小题及版面子节点通过 attrs JSON 往返。 */
export const QuestionGroupBlock = Node.create({
  name: 'questionGroup',
  group: 'block',
  atom: true,
  selectable: true,
  draggable: true,

  addAttributes() {
    return {
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