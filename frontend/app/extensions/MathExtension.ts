import { Node, mergeAttributes, InputRule, PasteRule } from '@tiptap/core'
import { VueNodeViewRenderer } from '@tiptap/vue-3'
import texmath from 'markdown-it-texmath'
import MathNode from '@/components/MathNode.vue'

export interface MathExtensionOptions {
  HTMLAttributes: Record<string, any>
  onEdit?: (payload: { latex: string, display: boolean, update: (attrs: any) => void }) => void
}

export const MathExtension = Node.create<MathExtensionOptions>({
  name: 'math',
  group: 'inline',
  inline: true,
  atom: true, // Treat as a single unit, not editable text

  addOptions() {
    return {
      HTMLAttributes: {},
      onEdit: undefined,
    }
  },

  addInputRules() {
    return [
      // Block math: $$...$$
      new InputRule({
        find: /\$\$([^$]+)\$\$$/,
        handler: ({ state, range, match }) => {
          const { tr } = state
          const start = range.from
          const end = range.to
          const latex = match[1]
          tr.replaceWith(start, end, this.type.create({ latex, display: true }))
        }
      }),
      // Inline math: $...$
      new InputRule({
        find: /\$([^$]+)\$$/,
        handler: ({ state, range, match }) => {
          const { tr } = state
          const start = range.from
          
          // Check if preceded by $ to avoid capturing part of $$...$$
          if (start > 0) {
            try {
              const prevChar = state.doc.textBetween(start - 1, start)
              if (prevChar === '$') {
                return null // Ignore, let the user finish typing $$
              }
            } catch (e) {
              // Ignore error if position is invalid
            }
          }

          const end = range.to
          const latex = match[1]
          tr.replaceWith(start, end, this.type.create({ latex, display: false }))
        }
      }),
      // Block math shortcut: $$<space>
      new InputRule({
        find: /^\$\$\s$/,
        handler: ({ state, range, match }) => {
          const { tr } = state
          const start = range.from
          const end = range.to
          tr.replaceWith(start, end, this.type.create({ latex: '', display: true }))
        }
      })
    ]
  },

  addNodeView() {
    return VueNodeViewRenderer(MathNode)
  },

  addAttributes() {
    return {
      latex: {
        default: '',
        parseHTML: element => element.getAttribute('data-latex'),
      },
      display: {
        default: false,
        parseHTML: element => element.getAttribute('data-display') === 'true',
      }
    }
  },

  parseHTML() {
    return [
      {
        tag: 'span[data-type="math"]',
      },
    ]
  },

  renderHTML({ node, HTMLAttributes }) {
    return [
      'span',
      mergeAttributes(this.options.HTMLAttributes, HTMLAttributes, {
        'data-type': 'math',
        'data-latex': node.attrs.latex,
        'data-display': node.attrs.display,
      }),
      node.attrs.display ? `$$${node.attrs.latex}$$` : `$${node.attrs.latex}$`
    ]
  },

  addStorage() {
    return {
      markdown: {
        serialize(state, node) {
          if (node.attrs.display) {
            state.write(`$$${node.attrs.latex}$$`)
          } else {
            state.write(`$${node.attrs.latex}$`)
          }
        },
        parse: {
          setup(md) {
            md.use(texmath, { delimiters: 'dollars' })
            // Normalise every texmath renderer to our custom node span
            const renderMath = (display: boolean) => (tokens: any[], idx: number) => {
              const content = tokens[idx].content
              return `<span data-type="math" data-latex="${md.utils.escapeHtml(content)}" data-display="${display}"></span>`
            }

            md.renderer.rules.math_inline = renderMath(false)
            md.renderer.rules.math_inline_double = renderMath(true)
            md.renderer.rules.math_block = renderMath(true)
            md.renderer.rules.math_block_eqno = renderMath(true)
          }
        }
      }
    }
  }
})
