import { describe, expect, it } from 'vitest'
import { formatBytes, groupMediaReferences, mediaReferenceLink } from '../mediaLibrary'

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
})
