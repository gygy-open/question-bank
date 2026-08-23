export function useImageUpload() {
    async function uploadImage(file: File): Promise<string> {
        const formData = new FormData()
        formData.append('file', file)

        const response = await fetch('/api/v1/upload/image', {
            method: 'POST',
            body: formData,
        })

        if (!response.ok) {
            throw new Error('图片上传失败')
        }

        const data = await response.json()
        return data.url as string
    }

    return { uploadImage }
}
