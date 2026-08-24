import type { RichDoc } from '@/types'

/**
 * schema 契约 fixture：覆盖 table / blank / math / image 四类关键节点。
 * 与后端 RichDoc 契约保持结构一致，供 schema 转换与只读渲染测试共用。
 */
export const richContentFixture: RichDoc = {
    type: 'doc',
    content: [
        {
            type: 'paragraph',
            content: [
                { type: 'text', text: '解方程 ' },
                { type: 'inlineMath', attrs: { latex: 'a^2 + b^2' } },
                { type: 'text', text: ' 的结果填入 ' },
                { type: 'blank', attrs: { blankId: 'blk_fixture_1' } },
                { type: 'text', text: ' 处。' },
            ],
        },
        {
            type: 'blockMath',
            attrs: { latex: '\\int_0^1 x\\,dx = \\frac{1}{2}' },
        },
        {
            type: 'image',
            attrs: {
                src: 'https://example.com/diagram.png',
                alt: '示意图',
                width: 152.4667,
                height: 113.4,
            },
        },
        {
            type: 'table',
            content: [
                {
                    type: 'tableRow',
                    content: [
                        {
                            type: 'tableHeader',
                            content: [
                                { type: 'paragraph', content: [{ type: 'text', text: '项' }] },
                            ],
                        },
                        {
                            type: 'tableHeader',
                            content: [
                                { type: 'paragraph', content: [{ type: 'text', text: '值' }] },
                            ],
                        },
                    ],
                },
                {
                    type: 'tableRow',
                    content: [
                        {
                            type: 'tableCell',
                            content: [
                                { type: 'paragraph', content: [{ type: 'text', text: '甲' }] },
                            ],
                        },
                        {
                            type: 'tableCell',
                            content: [
                                { type: 'paragraph', content: [{ type: 'text', text: '1' }] },
                            ],
                        },
                    ],
                },
            ],
        },
    ],
}

/** 仅含单个空段落的 doc：编辑器视为“空”，应输出 null。 */
export const emptyParagraphDoc: RichDoc = {
    type: 'doc',
    content: [{ type: 'paragraph' }],
}
