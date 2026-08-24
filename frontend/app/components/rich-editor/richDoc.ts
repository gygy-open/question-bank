import type { RichDoc, RichNode } from '@/types'

/** 生成稳定唯一的 blank id；优先 crypto.randomUUID，回退到时间戳+随机。 */
export function generateBlankId(): string {
    const g = globalThis as { crypto?: { randomUUID?: () => string } }
    if (g.crypto?.randomUUID) {
        return `blk_${g.crypto.randomUUID()}`
    }
    return `blk_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`
}

/** 按出现顺序收集 RichDoc 中所有 blank 节点的 blankId（与后端 collect_blank_ids 对齐）。 */
export function collectBlankIds(doc: RichDoc | null | undefined): string[] {
    const ids: string[] = []
    const walk = (node: RichNode): void => {
        if (node.type === 'blank') {
            const blankId = node.attrs?.blankId
            if (typeof blankId === 'string' && blankId) {
                ids.push(blankId)
            }
        }
        for (const child of node.content ?? []) {
            walk(child)
        }
    }
    if (doc) {
        for (const node of doc.content ?? []) {
            walk(node)
        }
    }
    return ids
}

/** 把 RichDoc 抽成纯文本（用于列表摘要/答案格式化），空 → ''。填空节点渲染为占位下划线。 */
export function richDocToPlainText(doc: RichDoc | null | undefined): string {
    if (!doc || doc.type !== 'doc') {
        return ''
    }
    const parts: string[] = []
    const walk = (node: RichNode): void => {
        if (node.type === 'text') {
            if (node.text) parts.push(node.text)
            return
        }
        if (node.type === 'blank') {
            parts.push('____')
            return
        }
        if (node.type === 'inlineMath' || node.type === 'blockMath') {
            const latex = node.attrs?.latex
            if (typeof latex === 'string' && latex) parts.push(latex)
            return
        }
        for (const child of node.content ?? []) {
            walk(child)
        }
        // 段落等块级节点之间补空格，避免文字粘连。
        if (node.type === 'paragraph') parts.push(' ')
    }
    for (const node of doc.content ?? []) {
        walk(node)
    }
    return parts.join('').replace(/\s+/g, ' ').trim()
}

function nodeHasContent(node: RichNode): boolean {
    if (node.type === 'text') {
        return !!node.text && node.text.length > 0
    }
    // 原子/叶子节点（图片、公式、填空、表格等）本身即内容。
    if (node.type !== 'paragraph') {
        return true
    }
    return (node.content ?? []).some(nodeHasContent)
}

/**
 * 判断 RichDoc 是否为“空”：null、无 content，或仅含空段落。
 * 编辑器用它决定输出 null 而非空 doc。
 */
export function isEmptyRichDoc(doc: RichDoc | null | undefined): boolean {
    if (!doc || doc.type !== 'doc') {
        return true
    }
    const content = doc.content ?? []
    if (content.length === 0) {
        return true
    }
    return content.every((node) => node.type === 'paragraph' && !nodeHasContent(node))
}
