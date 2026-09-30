import type { MediaReferenceItem } from '@/composables/useMedia'

export const MEDIA_OWNER_LABELS: Record<string, string> = {
    question: '题目',
    stimulus: '材料题',
    composition: '稿件',
    composition_version: '定稿版本',
}

const OWNER_ORDER = ['question', 'stimulus', 'composition', 'composition_version']

/** "被引用于"的跳转地址；已删除的引用方不给链接。 */
export function mediaReferenceLink(ref: MediaReferenceItem): string | null {
    if (ref.deleted) return null
    switch (ref.owner_type) {
        case 'question':
            return `/questions?id=${ref.owner_id}`
        case 'stimulus':
            return `/materials/${ref.owner_id}/edit`
        case 'composition':
            return ref.scope ? `/compositions/${ref.scope}/${ref.owner_id}` : null
        case 'composition_version':
            return ref.scope && ref.composition_id && ref.version_no
                ? `/compositions/${ref.scope}/${ref.composition_id}/versions/${ref.version_no}`
                : null
        default:
            return null
    }
}

export function groupMediaReferences(items: MediaReferenceItem[]): { type: string; label: string; items: MediaReferenceItem[] }[] {
    return OWNER_ORDER
        .map((type) => ({ type, label: MEDIA_OWNER_LABELS[type] ?? type, items: items.filter((i) => i.owner_type === type) }))
        .filter((group) => group.items.length > 0)
}

export function formatBytes(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
