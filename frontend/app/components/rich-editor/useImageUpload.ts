export function useImageUpload() {
    const { $api } = useNuxtApp()

    async function uploadImage(file: File): Promise<string> {
        const formData = new FormData()
        formData.append('file', file)
        try {
            const data = await $api<{ url: string }>('/upload/image', { method: 'POST', body: formData })
            return data.url
        } catch (error) {
            throw new Error('图片上传失败', { cause: error })
        }
    }

    return { uploadImage }
}
