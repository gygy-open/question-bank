// 给顶层块附加稳定 `uid` 全局属性，并在文档变更时自动补齐/去重。
// 这是「每段落=可独立定位/编号/引用的一行」的地基：拆分块 (keepOnSplit=false)、
// 复制粘贴产生的重复 uid 都会被 appendTransaction 重新赋值为新 UUID。
import { Extension } from '@tiptap/core'
import { Plugin, PluginKey } from '@tiptap/pm/state'
import { generateNodeId } from '@/lib/compositionDocument'

export interface UniqueIdOptions {
  types: string[]
  attrName: string
}

export const UniqueId = Extension.create<UniqueIdOptions>({
  name: 'compositionUniqueId',

  addOptions() {
    return { types: [], attrName: 'uid' }
  },

  addGlobalAttributes() {
    const { attrName } = this.options
    return [
      {
        types: this.options.types,
        attributes: {
          [attrName]: {
            default: null,
            parseHTML: (el) => el.getAttribute('data-uid'),
            renderHTML: (attrs) =>
              attrs[attrName] ? { 'data-uid': attrs[attrName] as string } : {},
            // 拆分块时不继承 uid，让 appendTransaction 给新块分配新的稳定标识。
            keepOnSplit: false,
          },
        },
      },
    ]
  },

  addProseMirrorPlugins() {
    const { types, attrName } = this.options
    const typeSet = new Set(types)
    return [
      new Plugin({
        key: new PluginKey('compositionUniqueId'),
        appendTransaction: (transactions, _oldState, newState) => {
          if (!transactions.some((t) => t.docChanged)) return null
          const seen = new Set<string>()
          const tr = newState.tr
          let modified = false
          newState.doc.descendants((node, pos) => {
            if (!typeSet.has(node.type.name)) return true
            const id = node.attrs[attrName] as string | null
            if (id == null || seen.has(id)) {
              const fresh = generateNodeId()
              tr.setNodeMarkup(pos, undefined, { ...node.attrs, [attrName]: fresh })
              seen.add(fresh)
              modified = true
            } else {
              seen.add(id)
            }
            // 顶层块的 uid 只在块本身，不下钻子节点（module 为 atom，无块级子节点）。
            return false
          })
          return modified ? tr : null
        },
      }),
    ]
  },
})
