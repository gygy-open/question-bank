import { generateHTML } from '@tiptap/core'
import katex from 'katex'
import type { RichDoc } from '@/types'
import { getSchemaExtensions } from './schemaExtensions'
import { isEmptyRichDoc } from './richDoc'

/**
 * 只读展示场景（题目列表/预览等），把 RichDoc 对象转成静态 HTML，不创建编辑器实例。
 * 对非法/未知输入做防御，返回空串而非抛错，避免列表整体崩溃。
 */
export function renderRichContentToHTML(doc: RichDoc | null | undefined): string {
    if (isEmptyRichDoc(doc) || !doc) {
        return ''
    }

    let html: string
    try {
        html = generateHTML(doc, getSchemaExtensions())
    } catch (error) {
        console.error('renderRichContentToHTML failed:', error)
        return ''
    }

    // generateHTML 不执行 nodeView，需要手动把 data-latex 渲染成 KaTeX
    if (typeof window === 'undefined') {
        return html
    }
    try {
        const parsed = new DOMParser().parseFromString(html, 'text/html')
        parsed.querySelectorAll<HTMLElement>('[data-latex]').forEach((el) => {
            const latex = el.getAttribute('data-latex') || ''
            const displayMode = el.getAttribute('data-type') === 'block-math'
            try {
                el.innerHTML = katex.renderToString(latex, { throwOnError: false, displayMode })
            } catch {
                el.textContent = latex
            }
        })
        return parsed.body.innerHTML
    } catch (error) {
        console.error('renderRichContentToHTML post-processing failed:', error)
        return html
    }
}
