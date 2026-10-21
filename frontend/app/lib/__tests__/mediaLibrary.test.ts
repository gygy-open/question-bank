import { describe, expect, it } from 'vitest'
import { formatBytes, groupMediaReferences, mediaReferenceLink, referenceKey, replaceableReferences, replaceSummary } from '../mediaLibrary'

const ref = (owner_type: string, extra: Record<string, unknown> = {}) => ({
    owner_type, owner_id: 7, title: 't', deleted: false, ...extra,
})

describe('mediaLibrary', () => {
    it('按引用方类型生成跳转地址，已删除的不给链接', () => {
        expect(mediaReferenceLink(ref('question'))).toBe('/questions?id=7')
        expect(mediaReferenceLink(ref('stimulus'))).toBe('/materials/7/edit')
        expect(mediaReferenceLink(ref('composition', { scope: 'shared' }))).toBe('/compositions/shared/7')
        expect(mediaReferenceLink(ref('composition_version', { scope: 'personal', composition_id: 3, version_no: 2 })))
            .toBe('/compositions/personal/3/versions/2')
        expect(mediaReferenceLink(ref('question', { deleted: true }))).toBeNull()
    })

    it('按固定顺序分组并省略空组', () => {
        const groups = groupMediaReferences([ref('composition'), ref('question'), ref('question')])
        expect(groups.map((g) => [g.label, g.items.length])).toEqual([['题目', 2], ['稿件', 1]])
    })

    it('格式化文件大小', () => {
        expect(formatBytes(512)).toBe('512 B')
        expect(formatBytes(2048)).toBe('2.0 KB')
        expect(formatBytes(3 * 1024 * 1024)).toBe('3.0 MB')
    })

    it('定稿版本不可替换', () => {
        const items = [ref('question'), ref('composition_version'), ref('stimulus'), ref('composition')]
        expect(replaceableReferences(items).map(referenceKey)).toEqual(['question-7', 'stimulus-7', 'composition-7'])
    })

    it('替换结果摘要只列出非零项', () => {
        expect(replaceSummary({ replaced: [{ owner_type: 'question', owner_id: 1 }], skipped: 0, frozen: 0 })).toBe('已替换 1 处引用')
        expect(replaceSummary({ replaced: [], skipped: 2, frozen: 1 })).toBe('已替换 0 处引用，2 处无权修改未替换，1 个定稿版本保持原图')
    })
})
