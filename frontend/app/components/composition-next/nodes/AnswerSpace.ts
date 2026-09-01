// 作答空间：atom 块节点，为试卷题目之间预留学生作答留白。
// props: lines(行数，控高) + style('blank' 空白 / 'lined' 答题横线)。
import { Node, mergeAttributes } from '@tiptap/core'
import { VueNodeViewRenderer } from '@tiptap/vue-3'
import AnswerSpaceView from './AnswerSpaceView.vue'

export const ANSWER_SPACE_MIN_LINES = 1
export const ANSWER_SPACE_MAX_LINES = 50

declare module '@tiptap/core' {
  interface Commands<ReturnType> {
    answerSpace: {
      setAnswerSpace: (attrs?: { lines?: number; style?: 'blank' | 'lined' }) => ReturnType
    }
  }
}

export const AnswerSpace = Node.create({
  name: 'answerSpace',
  group: 'block',
  atom: true,
  selectable: true,
  draggable: true,

  addAttributes() {
    return {
      lines: {
        default: 3,
        parseHTML: (el) => Number(el.getAttribute('data-lines')) || 3,
        renderHTML: (attrs) => ({ 'data-lines': String(attrs.lines) }),
      },
      style: {
        default: 'blank',
        parseHTML: (el) => (el.getAttribute('data-style') === 'lined' ? 'lined' : 'blank'),
        renderHTML: (attrs) => ({ 'data-style': String(attrs.style) }),
      },
    }
  },

  parseHTML() {
    return [{ tag: 'div[data-type="answer-space"]' }]
  },

  renderHTML({ HTMLAttributes }) {
    return [
      'div',
      mergeAttributes(HTMLAttributes, {
        'data-type': 'answer-space',
        class: 'composition-answer-space',
        role: 'separator',
        'aria-label': '作答空间',
      }),
    ]
  },

  addNodeView() {
    return VueNodeViewRenderer(AnswerSpaceView)
  },

  addCommands() {
    return {
      setAnswerSpace:
        (attrs) =>
        ({ commands }) =>
          commands.insertContent({
            type: this.name,
            attrs: { lines: attrs?.lines ?? 3, style: attrs?.style ?? 'blank' },
          }),
    }
  },
})
