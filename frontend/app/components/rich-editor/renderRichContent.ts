import { generateHTML } from '@tiptap/core'
import katex from 'katex'
import { getSchemaExtensions } from './schemaExtensions'

/** 只读展示场景（题目列表/预览等），把编辑器 JSON 转成静态 HTML，不创建编辑器实例。 */
export function renderRichContentToHTML(json: string | null | undefined): string {
    if (!json) {
        return ''
    }

    const html = generateHTML(JSON.parse(json), getSchemaExtensions())

    // generateHTML 不执行 nodeView，需要手动把 data-latex 渲染成 KaTeX
    if (typeof window === 'undefined') {
        return html
    }
    const doc = new DOMParser().parseFromString(html, 'text/html')
    doc.querySelectorAll<HTMLElement>('[data-latex]').forEach((el) => {
        const latex = el.getAttribute('data-latex') || ''
        const displayMode = el.getAttribute('data-type') === 'block-math'
        try {
            el.innerHTML = katex.renderToString(latex, { throwOnError: false, displayMode })
        } catch {
            el.textContent = latex
        }
    })
    return doc.body.innerHTML
}
