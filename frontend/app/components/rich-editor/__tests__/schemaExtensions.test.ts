import { describe, it, expect } from 'vitest'
import { generateHTML } from '@tiptap/core'
import { getSchemaExtensions } from '../schemaExtensions'
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

    it('包含 math 节点（携带 data-latex）', () => {
        expect(html).toContain('data-latex')
        expect(html).toContain('a^2 + b^2')
    })

    it('包含 image 节点', () => {
        expect(html).toContain('<img')
        expect(html).toContain('https://example.com/diagram.png')
    })
})
