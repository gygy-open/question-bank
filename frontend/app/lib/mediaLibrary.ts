import type { MediaAsset, MediaReferenceItem, MediaReplaceResult, MediaReplaceTarget } from '@/composables/useMedia'
import { translate } from '@/lib/locale'

const FORMAT_LABELS: Record<string, string> = { 'audio/mpeg': 'MP3', 'audio/mp4': 'M4A' }

export function mediaName(asset: Pick<MediaAsset, 'id' | 'kind' | 'original_filename'>): string {
    return asset.original_filename || translate(asset.kind === 'audio' ? 'media.unnamedAudio' : 'media.unnamedImage', { id: asset.id })
}

export function mediaFormat(mime: string): string {
    return FORMAT_LABELS[mime] ?? (mime.split('/')[1] ?? mime).toUpperCase()
}

/** 图片为宽×高，音频为时长。 */
export function mediaDimension(asset: Pick<MediaAsset, 'kind' | 'width' | 'height' | 'duration'>): string {
    if (asset.kind === 'audio') return formatDuration(asset.duration) || '—'
    return asset.width && asset.height ? `${asset.width}×${asset.height}` : '—'
}

const MEDIA_OWNER_LABEL_KEYS: Record<string, string> = {
    question: 'media.owner.question',
    stimulus: 'media.owner.stimulus',
    composition: 'media.owner.composition',
    composition_version: 'media.owner.compositionVersion',
}

/** 引用方类型（后端 owner_type）的显示名；未知类型原样返回。 */
export function mediaOwnerLabel(type: string): string {
    const key = MEDIA_OWNER_LABEL_KEYS[type]
    return key ? translate(key) : type
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
        .map((type) => ({ type, label: mediaOwnerLabel(type), items: items.filter((i) => i.owner_type === type) }))
        .filter((group) => group.items.length > 0)
}

export function formatBytes(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

/** 音频时长 m:ss（超过一小时为 h:mm:ss）。 */
export function formatDuration(seconds: number | null | undefined): string {
    if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return ''
    const total = Math.round(seconds)
    const h = Math.floor(total / 3600)
    const m = Math.floor((total % 3600) / 60)
    const s = String(total % 60).padStart(2, '0')
    return h ? `${h}:${String(m).padStart(2, '0')}:${s}` : `${m}:${s}`
}

/** 可被替换的引用：定稿版本永不改动。 */
export function replaceableReferences(items: MediaReferenceItem[]): (MediaReferenceItem & MediaReplaceTarget)[] {
    return items.filter((item): item is MediaReferenceItem & MediaReplaceTarget =>
        item.owner_type === 'question' || item.owner_type === 'stimulus' || item.owner_type === 'composition')
}

export function referenceKey(item: { owner_type: string; owner_id: number }): string {
    return `${item.owner_type}-${item.owner_id}`
}

export function replaceSummary(result: MediaReplaceResult): string {
    let summary = translate('media.replace.summary', { count: result.replaced.length })
    if (result.skipped) summary += translate('media.replace.summarySkipped', { count: result.skipped })
    if (result.frozen) summary += translate('media.replace.summaryFrozen', { count: result.frozen })
    return summary
}
