import { toast } from 'vue-sonner'
import { useMedia, useMediaSubject } from '@/composables/useMedia'
import { rememberRecentMedia } from '@/lib/recentMedia'

export interface UploadedImageAttrs {
    src: string
    assetId: number
}

/** 上传题目内容图片到学科媒体库；学科取宿主提供的媒体学科（见 provideMediaSubject）。 */
export function useImageUpload() {
    const mediaSubject = useMediaSubject()
    const { uploadContentImage } = useMedia()

    async function uploadImage(file: File): Promise<UploadedImageAttrs | null> {
        const subjectId = mediaSubject.value
        if (!subjectId) {
            toast.error('请先选择学科再插入图片')
            return null
        }
        try {
            const asset = await uploadContentImage(subjectId, file)
            rememberRecentMedia(subjectId, { id: asset.id, url: asset.url, name: asset.original_filename })
            return { src: asset.url, assetId: asset.id }
        } catch (error: any) {
            // 403 已由 api 插件统一提示。
            if (error?.response?.status !== 403) toast.error(error?.data?.detail || '图片上传失败')
            return null
        }
    }

    return { uploadImage }
}
