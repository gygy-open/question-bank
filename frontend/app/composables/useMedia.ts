import { computed, inject, provide, type InjectionKey, type Ref } from 'vue'

export type MediaKind = 'image' | 'audio'

/** 媒体选择器的结果，即插入编辑器节点的 attrs。 */
export interface MediaPickResult {
    src: string
    assetId: number
    /** 仅音频带文件名，作为播放器标题。 */
    title?: string | null
}

export interface MediaAsset {
    id: number
    url: string
    kind: MediaKind
    mime: string
    width?: number | null
    height?: number | null
    duration?: number | null
    displayable: boolean
    original_filename?: string | null
    alt?: string | null
    source?: string | null
    owner_user_id?: number | null
}

export interface MediaReferenceItem {
    owner_type: string
    owner_id: number
    title: string
    deleted: boolean
    composition_id?: number | null
    scope?: string | null
    version_no?: number | null
}

export interface MediaReferences {
    items: MediaReferenceItem[]
    hidden_count: number
}

export interface MediaAssetUpdate {
    original_filename?: string | null
    alt?: string | null
    source?: string | null
}

export interface MediaReplaceTarget {
    owner_type: 'question' | 'stimulus' | 'composition'
    owner_id: number
}

export interface MediaReplaceResult {
    replaced: MediaReplaceTarget[]
    skipped: number
    frozen: number
}

export type UserMediaPurpose = 'avatar' | 'chat'

export interface MediaAssetListItem extends MediaAsset {
    usage_count: number
    created_at: string
    byte_size: number
}

export interface MediaAssetPage {
    items: MediaAssetListItem[]
    total: number
    page: number
    size: number
}

export interface MediaListQuery {
    /** 不传则图片与音频都返回。 */
    kind?: MediaKind
    q?: string
    used?: boolean
    uploader_id?: number
    sort?: 'newest' | 'oldest' | 'name' | 'size'
    page?: number
    size?: number
}

/** 编辑器插图归属的学科；由稿件/材料/题目等宿主提供，未提供时回退当前工作学科。 */
const MEDIA_SUBJECT_KEY: InjectionKey<Ref<number | null>> = Symbol('media-subject')

export function provideMediaSubject(source: () => number | null | undefined) {
    const parent = inject(MEDIA_SUBJECT_KEY, null)
    provide(MEDIA_SUBJECT_KEY, computed(() => source() ?? parent?.value ?? null))
}

export function useMediaSubject(): Ref<number | null> {
    const injected = inject(MEDIA_SUBJECT_KEY, null)
    const { currentSubjectId } = useSubjectContext()
    return computed(() => injected?.value ?? currentSubjectId.value)
}

export function useMedia() {
    const { $api } = useNuxtApp()

    function toForm(file: File): FormData {
        const formData = new FormData()
        formData.append('file', file)
        return formData
    }

    async function uploadContentImage(subjectId: number, file: File): Promise<MediaAsset> {
        return await $api<MediaAsset>(`/subjects/${subjectId}/media`, { method: 'POST', body: toForm(file) })
    }

    async function uploadUserMedia(purpose: UserMediaPurpose, file: File): Promise<MediaAsset> {
        return await $api<MediaAsset>('/media/me', { method: 'POST', query: { purpose }, body: toForm(file) })
    }

    async function listSubjectMedia(subjectId: number, query: MediaListQuery = {}): Promise<MediaAssetPage> {
        return await $api<MediaAssetPage>(`/subjects/${subjectId}/media`, { query: { ...query } })
    }

    async function updateMedia(id: number, changes: MediaAssetUpdate): Promise<MediaAsset> {
        return await $api<MediaAsset>(`/media/${id}`, { method: 'PATCH', body: changes })
    }

    async function deleteMedia(id: number): Promise<void> {
        await $api(`/media/${id}`, { method: 'DELETE' })
    }

    async function getMediaReferences(id: number): Promise<MediaReferences> {
        return await $api<MediaReferences>(`/media/${id}/references`)
    }

    /** targets 缺省时替换全部可编辑的引用。 */
    async function replaceMedia(id: number, newAssetId: number, targets?: MediaReplaceTarget[]): Promise<MediaReplaceResult> {
        return await $api<MediaReplaceResult>(`/media/${id}/replace`, {
            method: 'POST',
            body: { new_asset_id: newAssetId, targets },
        })
    }

    return { uploadContentImage, uploadUserMedia, listSubjectMedia, updateMedia, deleteMedia, getMediaReferences, replaceMedia }
}

export interface MediaBatchResult {
    affected: number
    skipped: number
}

/** 媒体库批量操作与跨学科复制;均以当前学科为作用域。 */
export function useMediaBatch() {
    const { $api } = useNuxtApp()

    async function batchDelete(subjectId: number, ids: number[]): Promise<MediaBatchResult> {
        return await $api<MediaBatchResult>(`/subjects/${subjectId}/media/batch-delete`, { method: 'POST', body: { ids } })
    }

    async function batchUpdateSource(subjectId: number, ids: number[], source: string | null): Promise<MediaBatchResult> {
        return await $api<MediaBatchResult>(`/subjects/${subjectId}/media/batch-update`, { method: 'POST', body: { ids, source } })
    }

    /** 浏览器直接下载(cookie 鉴权),不经 $api。 */
    function archiveUrl(subjectId: number, ids: number[]): string {
        const query = ids.map(id => `ids=${id}`).join('&')
        return `/api/v1/subjects/${subjectId}/media/archive?${query}`
    }

    async function copyToSubject(assetId: number, subjectId: number): Promise<MediaAsset> {
        return await $api<MediaAsset>(`/media/${assetId}/copy`, { method: 'POST', body: { subject_id: subjectId } })
    }

    return { batchDelete, batchUpdateSource, archiveUrl, copyToSubject }
}
