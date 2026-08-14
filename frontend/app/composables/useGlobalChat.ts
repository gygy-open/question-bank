// Global AI assistant chat state.
// Module-scoped singletons (not useState) so File objects and in-flight
// streaming requests survive component unmount — closing the floating widget
// must NOT interrupt an ongoing generation.
import { useLocalStorage } from '@vueuse/core'

export interface ChatMessage {
    id?: number
    role: 'user' | 'assistant' | 'system' | 'tool'
    content: string
    images?: string[]
    tool_calls?: any[]
    actions?: any[]
    proposal?: any
}

export interface ChatSession {
    id: string
    title: string
    updated_at: string
}

interface AIModel {
    id: number
    name: string
    is_vision_capable?: boolean
}

interface AIProvider {
    id: number
    name: string
    models: AIModel[]
}

const SESSION_LIMIT = 20
const MESSAGE_LIMIT = 20

// --- UI state ---
const isOpen = ref(false)
const isMinimized = ref(false)
const view = ref<'chat' | 'history'>('chat')
const isSelectionMode = ref(false)
const selectedMessageIndices = ref<Set<number>>(new Set())
const hasUnread = ref(false)
const isPromptManagerOpen = ref(false)
const previewImage = ref<string | null>(null)
const isPreviewOpen = ref(false)

// Persisted geometry
const position = useLocalStorage('qb-chat-widget-position', { x: -1, y: -1 })
const size = useLocalStorage('qb-chat-widget-size', { width: 400, height: 600 })

// --- Data state ---
const sessions = ref<ChatSession[]>([])
const hasMoreSessions = ref(false)
const isLoadingMoreSessions = ref(false)
const editingSessionId = ref<string | null>(null)
const editTitle = ref('')

const currentSessionId = ref<string | null>(null)
const messages = ref<ChatMessage[]>([])
const input = ref('')
const selectedImages = ref<string[]>([]) // DataURL previews
const selectedFiles = ref<File[]>([]) // actual files to upload
const loading = ref(false)
const isLoadingMore = ref(false)
const hasMore = ref(false)
const providers = ref<AIProvider[]>([])
const selectedModelId = ref<string>('')
const isInitialized = ref(false)

// --- Computed ---
const allModels = computed(() =>
    providers.value.flatMap(p =>
        p.models.map(m => ({
            ...m,
            providerName: p.name,
            displayName: `${p.name} - ${m.name}`,
        }))
    )
)

const currentModel = computed(() =>
    allModels.value.find(m => m.id.toString() === selectedModelId.value)
)

const isVisionCapable = computed(() => currentModel.value?.is_vision_capable ?? false)

const currentTitle = computed(() => {
    if (!currentSessionId.value) return '新对话'
    return sessions.value.find(s => s.id === currentSessionId.value)?.title || '对话'
})

// Clearing images when switching to a non-vision model.
watch(selectedModelId, () => {
    if (!isVisionCapable.value) {
        selectedImages.value = []
        selectedFiles.value = []
    }
})

// --- Data fetching ---
const fetchSessions = async (loadMore = false) => {
    const { $api } = useNuxtApp()
    try {
        if (loadMore) isLoadingMoreSessions.value = true
        const skip = loadMore ? sessions.value.length : 0
        const data = await $api<ChatSession[]>(`/chat/sessions?skip=${skip}&limit=${SESSION_LIMIT}`)
        if (loadMore) {
            sessions.value.push(...data)
        } else {
            sessions.value = data
        }
        hasMoreSessions.value = data.length === SESSION_LIMIT
    } catch (e) {
        console.error('Failed to fetch sessions', e)
    } finally {
        if (loadMore) isLoadingMoreSessions.value = false
    }
}

const loadSession = async (sessionId: string) => {
    const { $api } = useNuxtApp()
    if (String(currentSessionId.value) === String(sessionId)) {
        view.value = 'chat'
        return
    }
    try {
        loading.value = true
        messages.value = []
        hasMore.value = false
        currentSessionId.value = sessionId
        await $api<any>(`/chat/sessions/${sessionId}`)
        const msgs = await $api<any[]>(`/chat/sessions/${sessionId}/messages?skip=0&limit=${MESSAGE_LIMIT}`)
        messages.value = msgs.map((m: any) => ({
            id: m.id,
            role: m.role,
            content: m.content || '',
            images: m.images,
            tool_calls: m.tool_calls,
        }))
        hasMore.value = msgs.length === MESSAGE_LIMIT
        view.value = 'chat'
    } catch (e) {
        console.error('Failed to load session', e)
    } finally {
        loading.value = false
    }
}

const loadMore = async () => {
    const { $api } = useNuxtApp()
    if (!currentSessionId.value || isLoadingMore.value) return
    try {
        isLoadingMore.value = true
        const skip = messages.value.length
        const msgs = await $api<any[]>(`/chat/sessions/${currentSessionId.value}/messages?skip=${skip}&limit=${MESSAGE_LIMIT}`)
        if (msgs.length < MESSAGE_LIMIT) hasMore.value = false
        const newMessages = msgs.map((m: any) => ({
            id: m.id,
            role: m.role,
            content: m.content || '',
            images: m.images,
            tool_calls: m.tool_calls,
        }))
        messages.value = [...newMessages, ...messages.value]
    } catch (e) {
        console.error('Failed to load more messages', e)
    } finally {
        isLoadingMore.value = false
    }
}

const createNewSession = () => {
    currentSessionId.value = null
    messages.value = []
    input.value = ''
    selectedImages.value = []
    selectedFiles.value = []
    hasMore.value = false
    view.value = 'chat'
}

// --- Session title editing ---
const startEditing = (session: ChatSession, event: Event) => {
    event.stopPropagation()
    editingSessionId.value = session.id
    editTitle.value = session.title || '新对话'
}

const saveTitle = async () => {
    const { $api } = useNuxtApp()
    if (!editingSessionId.value) return
    const sessionId = editingSessionId.value
    const newTitle = editTitle.value.trim()
    const session = sessions.value.find(s => s.id === sessionId)
    if (!newTitle || (session && session.title === newTitle)) {
        editingSessionId.value = null
        return
    }
    try {
        if (session) session.title = newTitle
        await $api(`/chat/sessions/${sessionId}`, { method: 'PATCH', body: { title: newTitle } })
    } catch (e) {
        console.error('Failed to update session title', e)
        fetchSessions()
    } finally {
        editingSessionId.value = null
    }
}

const cancelEditing = () => {
    editingSessionId.value = null
}

const deleteSession = async (sessionId: string, event: Event) => {
    const { $api } = useNuxtApp()
    event.stopPropagation()
    if (!confirm('确定要删除这个对话吗？')) return
    try {
        await $api(`/chat/sessions/${sessionId}`, { method: 'DELETE' })
        sessions.value = sessions.value.filter(s => s.id !== sessionId)
        if (currentSessionId.value === sessionId) createNewSession()
    } catch (e) {
        console.error('Failed to delete session', e)
    }
}

// --- Message editing ---
const handleUpdateMessage = async (event: { id: number; content: string }) => {
    const { $api } = useNuxtApp()
    try {
        await $api(`/chat/messages/${event.id}`, { method: 'PATCH', body: { content: event.content } })
        const msg = messages.value.find(m => m.id === event.id)
        if (msg) msg.content = event.content
    } catch (e) {
        console.error('Failed to update message', e)
    }
}

const handleDeleteMessage = async (id: number) => {
    const { $api } = useNuxtApp()
    try {
        await $api(`/chat/messages/${id}`, { method: 'DELETE' })
        messages.value = messages.value.filter(m => m.id !== id)
    } catch (e) {
        console.error('Failed to delete message', e)
    }
}

// --- Image handling ---
const addFiles = (files: File[]) => {
    for (const file of files) {
        if (!file.type.startsWith('image/')) continue
        selectedFiles.value.push(file)
        const reader = new FileReader()
        reader.onload = e => {
            if (e.target?.result) selectedImages.value.push(e.target.result as string)
        }
        reader.readAsDataURL(file)
    }
}

const removeImage = (index: number) => {
    selectedImages.value.splice(index, 1)
    selectedFiles.value.splice(index, 1)
}

const openPreview = (img: string) => {
    previewImage.value = img
    isPreviewOpen.value = true
}

// --- Selection mode ---
const toggleSelectionMode = () => {
    isSelectionMode.value = !isSelectionMode.value
    selectedMessageIndices.value.clear()
}

const toggleMessageSelection = (index: number) => {
    if (selectedMessageIndices.value.has(index)) {
        selectedMessageIndices.value.delete(index)
    } else {
        selectedMessageIndices.value.add(index)
    }
    // Trigger reactivity for Set mutation.
    selectedMessageIndices.value = new Set(selectedMessageIndices.value)
}

const copySelectedMessages = () => {
    const indices = Array.from(selectedMessageIndices.value).sort((a, b) => a - b)
    const text = indices
        .map(i => messages.value[i])
        .filter(Boolean)
        .map(m => {
            const role = m.role === 'user' ? 'User' : 'Assistant'
            return `**${role}:**\n${m.content}`
        })
        .join('\n\n---\n\n')
    navigator.clipboard.writeText(text)
    isSelectionMode.value = false
    selectedMessageIndices.value = new Set()
}

const handlePromptSelect = (content: string) => {
    input.value = input.value ? `${input.value}\n${content}` : content
}

// --- Send message (streaming) ---
// This runs entirely at module scope; it does not depend on any component
// instance, so an in-flight generation keeps updating `messages` even after
// the widget is closed/unmounted.
const sendMessage = async () => {
    const { $api } = useNuxtApp()
    if ((!input.value.trim() && selectedFiles.value.length === 0) || !selectedModelId.value || loading.value) return

    const userMessageContent = input.value.trim()
    const userImagesPreviews = [...selectedImages.value]
    const userFiles = [...selectedFiles.value]

    input.value = ''
    selectedImages.value = []
    selectedFiles.value = []
    loading.value = true

    try {
        // 1. Create session if needed (no navigation — same function continues).
        if (!currentSessionId.value) {
            const session = await $api<ChatSession>('/chat/sessions', {
                method: 'POST',
                body: { title: '新对话' },
            })
            currentSessionId.value = session.id
            await fetchSessions()
        }

        // Optimistic messages.
        messages.value.push({
            role: 'user',
            content: userMessageContent,
            images: userImagesPreviews.length > 0 ? userImagesPreviews : undefined,
        })
        messages.value.push({ role: 'assistant', content: '', actions: [] })

        // 2. Upload images.
        const uploadedImagePaths: string[] = []
        for (const file of userFiles) {
            const formData = new FormData()
            formData.append('file', file)
            const res = await $api<{ url: string }>('/upload/image', { method: 'POST', body: formData })
            uploadedImagePaths.push(res.url)
        }

        // 3. Stream response.
        const token = useCookie('token').value
        const response = await fetch(`/api/v1/chat/sessions/${currentSessionId.value}/messages`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(token ? { Authorization: `Bearer ${token}` } : {}),
            },
            body: JSON.stringify({
                model_id: parseInt(selectedModelId.value),
                message: {
                    role: 'user',
                    content: userMessageContent,
                    images: uploadedImagePaths.length > 0 ? uploadedImagePaths : undefined,
                },
                subject_id: useSubjectContext().currentSubjectId.value ?? undefined,
                stream: true,
            }),
        })

        if (!response.ok) throw new Error(response.statusText)
        if (!response.body) throw new Error('No response body')

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let assistantMessage = ''

        while (true) {
            const { done, value } = await reader.read()
            if (done) break
            buffer += decoder.decode(value, { stream: true })
            const lines = buffer.split('\n\n')
            buffer = lines.pop() || ''

            for (const line of lines) {
                const eventMatch = line.match(/^event: (.*)$/m)
                const dataMatch = line.match(/^data: (.*)$/m)
                if (!eventMatch || !dataMatch) continue

                const event = eventMatch[1].trim()
                const dataStr = dataMatch[1].trim()
                try {
                    const data = JSON.parse(dataStr)
                    if (messages.value.length === 0) continue
                    const last = messages.value[messages.value.length - 1]

                    if (event === 'message') {
                        assistantMessage += data
                        last.content = assistantMessage
                    } else if (event === 'action') {
                        if (!last.actions) last.actions = []
                        last.actions.push({ tool: data.tool, input: data.input, status: 'running' })
                    } else if (event === 'action_result') {
                        const actions = last.actions
                        if (actions && actions.length > 0) {
                            const lastAction = actions[actions.length - 1]
                            if (lastAction.tool === data.tool) {
                                lastAction.status = 'completed'
                                lastAction.output = data.output
                            }
                        }
                    } else if (event === 'proposal') {
                        last.proposal = data
                    } else if (event === 'message_meta') {
                        if (data.role === 'user' && messages.value.length >= 2) {
                            messages.value[messages.value.length - 2].id = data.id
                        } else if (data.role === 'assistant') {
                            last.id = data.id
                        }
                    }
                } catch (e) {
                    console.error('SSE parse error', e)
                }
            }
        }

        fetchSessions()
        // Surface an unread indicator if the user closed the widget mid-stream.
        if (!isOpen.value || isMinimized.value) hasUnread.value = true
    } catch (e) {
        console.error('Chat error', e)
        if (messages.value.length > 0) {
            messages.value[messages.value.length - 1].content += '\n[Error: Failed to generate response]'
        }
    } finally {
        loading.value = false
    }
}

// --- Widget controls ---
const initialize = async () => {
    if (isInitialized.value) return
    isInitialized.value = true
    const { $api } = useNuxtApp()
    try {
        const data = await $api<AIProvider[]>('/ai-config/providers')
        providers.value = data
        if (allModels.value.length > 0 && !selectedModelId.value) {
            selectedModelId.value = allModels.value[0].id.toString()
        }
        await fetchSessions()
    } catch (e) {
        console.error('Failed to initialize chat', e)
        isInitialized.value = false
    }
}

const open = () => {
    isOpen.value = true
    isMinimized.value = false
    hasUnread.value = false
    initialize()
}

const close = () => {
    isOpen.value = false
}

const toggle = () => {
    if (isOpen.value && !isMinimized.value) {
        close()
    } else {
        open()
    }
}

const minimize = () => {
    isMinimized.value = true
}

const restore = () => {
    isMinimized.value = false
    hasUnread.value = false
}

const resetGeometry = () => {
    position.value = { x: -1, y: -1 }
    size.value = { width: 400, height: 600 }
}

export const useGlobalChat = () => ({
    // UI state
    isOpen,
    isMinimized,
    view,
    isSelectionMode,
    selectedMessageIndices,
    hasUnread,
    isPromptManagerOpen,
    previewImage,
    isPreviewOpen,
    position,
    size,
    // Data state
    sessions,
    hasMoreSessions,
    isLoadingMoreSessions,
    editingSessionId,
    editTitle,
    currentSessionId,
    messages,
    input,
    selectedImages,
    selectedFiles,
    loading,
    isLoadingMore,
    hasMore,
    providers,
    selectedModelId,
    // Computed
    allModels,
    currentModel,
    isVisionCapable,
    currentTitle,
    // Methods
    fetchSessions,
    loadSession,
    loadMore,
    createNewSession,
    startEditing,
    saveTitle,
    cancelEditing,
    deleteSession,
    handleUpdateMessage,
    handleDeleteMessage,
    addFiles,
    removeImage,
    openPreview,
    toggleSelectionMode,
    toggleMessageSelection,
    copySelectedMessages,
    handlePromptSelect,
    sendMessage,
    initialize,
    open,
    close,
    toggle,
    minimize,
    restore,
    resetGeometry,
})
