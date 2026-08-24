import { describe, it, expect } from 'vitest'
import type { RichDoc } from '@/types'
import { isEmptyRichDoc } from '../richDoc'
import { renderRichContentToHTML } from '../renderRichContent'
import { richContentFixture, emptyParagraphDoc } from './richContent.fixture'

describe('isEmptyRichDoc', () => {
    it('null / undefined 视为空', () => {
        expect(isEmptyRichDoc(null)).toBe(true)
        expect(isEmptyRichDoc(undefined)).toBe(true)
    })

    it('无 content 或仅空段落视为空', () => {
        expect(isEmptyRichDoc({ type: 'doc' })).toBe(true)
        expect(isEmptyRichDoc({ type: 'doc', content: [] })).toBe(true)
        expect(isEmptyRichDoc(emptyParagraphDoc)).toBe(true)
    })

    it('含文本或原子节点视为非空', () => {
        const withText: RichDoc = {
            type: 'doc',
            content: [{ type: 'paragraph', content: [{ type: 'text', text: 'x' }] }],
        }
        const withBlank: RichDoc = {
            type: 'doc',
            content: [
                { type: 'paragraph', content: [{ type: 'blank', attrs: { blankId: 'b1' } }] },
            ],
        }
        expect(isEmptyRichDoc(withText)).toBe(false)
        expect(isEmptyRichDoc(withBlank)).toBe(false)
    })
})

describe('renderRichContentToHTML', () => {
    it('渲染 fixture 得到非空 HTML 并处理 KaTeX', () => {
        const html = renderRichContentToHTML(richContentFixture)
        expect(html).toBeTruthy()
        expect(html).toContain('<table')
        expect(html).toContain('<img')
        expect(html).toContain('width="152.4667"')
        expect(html).toContain('height="113.4"')
        // window 存在时会把 data-latex 渲染成 KaTeX
        expect(html).toContain('katex')
    })

    it('空内容返回空串', () => {
        expect(renderRichContentToHTML(null)).toBe('')
        expect(renderRichContentToHTML(emptyParagraphDoc)).toBe('')
    })

    it('非法输入不抛错，降级为空串', () => {
        const broken = { type: 'doc', content: [{ type: 'no_such_node' }] } as unknown as RichDoc
        expect(() => renderRichContentToHTML(broken)).not.toThrow()
        expect(renderRichContentToHTML(broken)).toBe('')
    })
})
