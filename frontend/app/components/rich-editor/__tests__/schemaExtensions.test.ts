import { describe, it, expect } from 'vitest'
import { generateHTML, generateJSON } from '@tiptap/core'
import type { RichDoc } from '@/types'
import { getSchemaExtensions, clampBlankWidthEm } from '../schemaExtensions'
import { richContentFixture } from './richContent.fixture'

describe('getSchemaExtensions schema 契约', () => {
    const html = generateHTML(richContentFixture, getSchemaExtensions())

    it('转换 fixture 产出非空 HTML', () => {
        expect(html).toBeTruthy()
        expect(html.length).toBeGreaterThan(0)
    })

    it('包含 table 节点', () => {
        expect(html).toContain('<table')
        expect(html).toContain('</table>')
    })

    it('包含 blank 节点及其 blankId', () => {
        expect(html).toContain('data-type="blank"')
        expect(html).toContain('data-blank-id="blk_fixture_1"')
    })

    it('缺省 widthEm 的 blank 渲染默认宽度', () => {
        expect(html).toContain('data-width-em="4"')
        expect(html).toContain('width: 4em')
    })

    it('包含 math 节点（携带 data-latex）', () => {
        expect(html).toContain('data-latex')
        expect(html).toContain('a^2 + b^2')
    })

    it('包含 image 节点', () => {
        expect(html).toContain('<img')
        expect(html).toContain('https://example.com/diagram.png')
    })
})
describe('blank widthEm 渲染与规整', () => {
    function blankHtml(widthEm: unknown): string {
        const doc: RichDoc = {
            type: 'doc',
            content: [
                {
                    type: 'paragraph',
                    content: [{ type: 'blank', attrs: { blankId: 'b1', widthEm } }],
                },
            ],
        }
        return generateHTML(doc, getSchemaExtensions())
    }

    it('按 widthEm 输出对应宽度', () => {
        expect(blankHtml(8)).toContain('width: 8em')
        expect(blankHtml(8)).toContain('data-width-em="8"')
    })

    it('从 HTML 回读 widthEm', () => {
        const doc = generateJSON(
            '<p><span data-type="blank" data-blank-id="b1" data-width-em="8"></span></p>',
            getSchemaExtensions(),
        )
        expect(doc.content?.[0]?.content?.[0]?.attrs).toMatchObject({
            blankId: 'b1',
            widthEm: 8,
        })
    })

    it('越界 widthEm 被夹到 [2, 30]', () => {
        expect(blankHtml(1)).toContain('width: 2em')
        expect(blankHtml(99)).toContain('width: 30em')
    })

    it('clampBlankWidthEm 处理非法输入回退默认', () => {
        expect(clampBlankWidthEm(undefined)).toBe(4)
        expect(clampBlankWidthEm('abc')).toBe(4)
        expect(clampBlankWidthEm(NaN)).toBe(4)
        expect(clampBlankWidthEm(1)).toBe(2)
        expect(clampBlankWidthEm(31)).toBe(30)
        expect(clampBlankWidthEm(6.4)).toBe(6)
    })
})
