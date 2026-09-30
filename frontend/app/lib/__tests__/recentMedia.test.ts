import { describe, expect, it } from 'vitest'
import { RECENT_MEDIA_LIMIT, loadRecentMedia, pushRecentMedia, rememberRecentMedia } from '../recentMedia'

function memoryStorage(initial: Record<string, string> = {}) {
    const data = { ...initial }
    return {
        data,
        getItem: (key: string) => data[key] ?? null,
        setItem: (key: string, value: string) => { data[key] = value },
    }
}

const entry = (id: number) => ({ id, url: `/api/v1/media/${id}/content` })

describe('recentMedia', () => {
    it('最近插入的排最前，同一资产去重，超出上限截断', () => {
        let list = [entry(1), entry(2)]
        list = pushRecentMedia(list, entry(2))
        expect(list.map((e) => e.id)).toEqual([2, 1])

        for (let i = 3; i < RECENT_MEDIA_LIMIT + 5; i++) list = pushRecentMedia(list, entry(i))
        expect(list).toHaveLength(RECENT_MEDIA_LIMIT)
        expect(list[0]?.id).toBe(RECENT_MEDIA_LIMIT + 4)
    })

    it('按学科分开存储', () => {
        const storage = memoryStorage()
        rememberRecentMedia(1, entry(10), storage)
        rememberRecentMedia(2, entry(20), storage)
        expect(loadRecentMedia(1, storage).map((e) => e.id)).toEqual([10])
        expect(loadRecentMedia(2, storage).map((e) => e.id)).toEqual([20])
    })

    it('损坏或非法的存储内容回退为空/过滤掉', () => {
        expect(loadRecentMedia(1, memoryStorage({ 'qb:recent-media:1': '{bad' }))).toEqual([])
        const mixed = JSON.stringify([entry(5), { id: 'x', url: 1 }, null])
        expect(loadRecentMedia(1, memoryStorage({ 'qb:recent-media:1': mixed })).map((e) => e.id)).toEqual([5])
    })
})
