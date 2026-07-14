// Global state to hold pending message across route changes
// We use a global ref instead of useState because useState serializes data,
// which breaks File objects.
const globalPendingMessage = ref<{
    content: string
    images: string[]
    files: File[]
    modelId: string
} | null>(null)

export const useChatState = () => {
    return { pendingMessage: globalPendingMessage }
}
