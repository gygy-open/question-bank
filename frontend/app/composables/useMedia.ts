import { computed, inject, provide, type InjectionKey, type Ref } from 'vue'

export interface MediaAsset {
    id: number
    url: string
    mime: string
    width?: number | null
    height?: number | null
    displayable: boolean
    original_filename?: string | null
}

export type UserMediaPurpose = 'avatar' | 'chat'

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

    return { uploadContentImage, uploadUserMedia }
}
