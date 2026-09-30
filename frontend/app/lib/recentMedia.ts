/** 编辑器"最近使用"的图片：按学科存在 localStorage，只存展示所需的最少字段。 */
export interface RecentMediaEntry {
    id: number
    url: string
    name?: string | null
}

export const RECENT_MEDIA_LIMIT = 24

const storageKey = (subjectId: number) => `qb:recent-media:${subjectId}`

export function pushRecentMedia(list: RecentMediaEntry[], entry: RecentMediaEntry): RecentMediaEntry[] {
    return [entry, ...list.filter((item) => item.id !== entry.id)].slice(0, RECENT_MEDIA_LIMIT)
}

function isEntry(value: unknown): value is RecentMediaEntry {
    const v = value as RecentMediaEntry
    return !!v && Number.isInteger(v.id) && v.id > 0 && typeof v.url === 'string'
}

export function loadRecentMedia(subjectId: number, storage: Pick<Storage, 'getItem'> = localStorage): RecentMediaEntry[] {
    try {
        const parsed = JSON.parse(storage.getItem(storageKey(subjectId)) ?? '[]')
        return Array.isArray(parsed) ? parsed.filter(isEntry).slice(0, RECENT_MEDIA_LIMIT) : []
    } catch {
        return []
    }
}

export function rememberRecentMedia(
    subjectId: number,
    entry: RecentMediaEntry,
    storage: Pick<Storage, 'getItem' | 'setItem'> = localStorage,
): void {
    try {
        storage.setItem(storageKey(subjectId), JSON.stringify(pushRecentMedia(loadRecentMedia(subjectId, storage), entry)))
    } catch {
        // 存储不可用（隐私模式/配额）时"最近使用"只是缺省为空，不影响插图。
    }
}
