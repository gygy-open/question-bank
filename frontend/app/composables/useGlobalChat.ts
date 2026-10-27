// Global AI assistant chat state.
// Module-scoped singletons (not useState) so File objects and in-flight
// streaming requests survive component unmount — closing the side panel
// must NOT interrupt an ongoing generation.
import { useLocalStorage } from '@vueuse/core'
import {
    completeChatAction,
    createChatAction,
    failRunningChatActions,
    finalizeChatStream,
    type ChatAction,
} from '@/lib/chatStream'
import { applyChatMessageMeta, nextChatMessageUiId } from '@/lib/chatMessages'
import type { AIProvider, UserAIPreference } from '@/types/ai-config'
import { pickChatModel } from '@/lib/ai-config'
import { currentLocale, translate } from '@/lib/locale'

export interface ChatMessage {
    // Stable client-side identity, assigned at creation and never changed — used
    // to key the list so an optimistic message survives the `message_meta` id update.
    uiId: string
    id?: number
    role: 'user' | 'assistant' | 'system' | 'tool'
    content: string
    images?: string[]
    tool_calls?: any[]
    actions?: ChatAction[]
    proposal?: any
}

export interface ChatSession {
    id: string
    title: string
    updated_at: string
}

const SESSION_LIMIT = 20
const MESSAGE_LIMIT = 20

// --- UI state ---
// Persisted so the panel stays docked across reloads.
const isOpen = useLocalStorage('qb-chat-panel-open', false)
// Expanded: the docked panel overlays the whole content area.
const isExpanded = ref(false)
const view = ref<'chat' | 'history'>('chat')
const isSelectionMode = ref(false)
const selectedMessageIndices = ref<Set<number>>(new Set())
const hasUnread = ref(false)
const isPromptManagerOpen = ref(false)
const previewImage = ref<string | null>(null)
const isPreviewOpen = ref(false)

// Persisted width of the docked side panel
export const CHAT_PANEL_DEFAULT_WIDTH = 400
const panelWidth = useLocalStorage('qb-chat-panel-width', CHAT_PANEL_DEFAULT_WIDTH)

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
// 只列可对话的模型：排除向量模型和已停用的服务商；个人服务商排在前面。
const allModels = computed(() =>
    providers.value
        .filter(p => p.is_active)
        .flatMap(p =>
            p.models
                .filter(m => !m.is_embedding_model)
                .map(m => ({
                    ...m,
                    providerName: p.name,
                    isPersonal: p.is_personal,
                    displayName: `${p.name} - ${m.name}`,
                }))
        )
        .sort((a, b) => Number(b.isPersonal) - Number(a.isPersonal))
)

const currentModel = computed(() =>
    allModels.value.find(m => m.id.toString() === selectedModelId.value)
)

const isVisionCapable = computed(() => currentModel.value?.is_vision_capable ?? false)

const currentTitle = computed(() => {
    if (!currentSessionId.value) return translate('chat.newSession')
    return sessions.value.find(s => s.id === currentSessionId.value)?.title || translate('chat.untitled')
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
            uiId: nextChatMessageUiId(),
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
            uiId: nextChatMessageUiId(),
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
    editTitle.value = session.title || translate('chat.newSession')
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
    if (!confirm(translate('chat.history.deleteConfirm'))) return
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
// the panel is closed/unmounted.
const sendMessage = async () => {
    const nuxtApp = useNuxtApp()
    const { $api } = nuxtApp
    const { uploadUserMedia } = useMedia()
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
                body: { title: translate('chat.newSession') },
            })
            currentSessionId.value = session.id
            await fetchSessions()
        }

        // Optimistic messages.
        messages.value.push({
            uiId: nextChatMessageUiId(),
            role: 'user',
            content: userMessageContent,
            images: userImagesPreviews.length > 0 ? userImagesPreviews : undefined,
        })
        messages.value.push({ uiId: nextChatMessageUiId(), role: 'assistant', content: '', actions: [] })

        // 2. Upload images.
        const uploadedImagePaths: string[] = []
        for (const file of userFiles) {
            const asset = await uploadUserMedia('chat', file)
            uploadedImagePaths.push(asset.url)
        }

        // 3. Stream response.
        const token = useCookie('token').value
        const aiScene = useAiScene()
        const response = await fetch(`/api/v1/chat/sessions/${currentSessionId.value}/messages`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                // 原生 fetch 不经过 plugins/api.ts，需自行带上界面语言（决定 AI 回复语言）。
                'Accept-Language': currentLocale.value,
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
                scene: aiScene.scene.value ?? undefined,
                scene_context: aiScene.context.value ?? undefined,
                stream: true,
            }),
        })

        if (!response.ok) throw new Error(response.statusText)
        if (!response.body) throw new Error('No response body')

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let assistantMessage = ''
        let receivedDone = false

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
                const data = JSON.parse(dataStr)
                if (messages.value.length === 0) continue
                const last = messages.value[messages.value.length - 1]

                if (event === 'message') {
                    assistantMessage += data
                    last.content = assistantMessage
                } else if (event === 'action') {
                    if (!last.actions) last.actions = []
                    last.actions.push(createChatAction(data))
                } else if (event === 'action_result') {
                    if (last.actions) completeChatAction(last.actions, data)
                } else if (event === 'proposal') {
                    last.proposal = data
                } else if (event === 'client_tool') {
                    // Fire-and-forget: the backend is parked on a ticket with its own
                    // timeout, so awaiting here would stall SSE reading.
                    if (!last.actions) last.actions = []
                    last.actions.push(createChatAction(data))
                    // Re-establish Nuxt's async context: we're deep inside raw stream reads here,
                    // which already crossed several awaits outside Nuxt's composable tracking.
                    nuxtApp.runWithContext(() => useAiClientTools().handleRequest(data))
                } else if (event === 'message_meta') {
                    // Attach the backend id to the optimistic message; uiId stays put.
                    applyChatMessageMeta(messages.value, data)
                } else if (event === 'done') {
                    receivedDone = true
                }
            }
        }

        const last = messages.value[messages.value.length - 1]
        if (!finalizeChatStream(last?.actions ?? [], receivedDone)) {
            throw new Error('SSE stream ended before done')
        }

        fetchSessions()
        // Surface an unread indicator if the user closed the panel mid-stream.
        if (!isOpen.value) hasUnread.value = true
    } catch (e) {
        console.error('Chat error', e)
        if (messages.value.length > 0) {
            const last = messages.value[messages.value.length - 1]
            if (last.actions) failRunningChatActions(last.actions)
            const interruption = `[Error: ${translate('chat.errors.interrupted')}]`
            if (!last.content.includes(interruption)) last.content += `\n${interruption}`
        }
    } finally {
        loading.value = false
    }
}

// --- Widget controls ---
// 上次应用的默认模型。默认模型变了（用户在设置里改了偏好或管理员改了全局）就跟着切换；
// 没变时保留用户在聊天框里的手动选择。
let appliedDefaultId: number | null | undefined

/** 重新拉取可用模型与默认模型。每次打开助手、以及 AI 设置变更后调用。 */
const refreshModels = async () => {
    const { $api } = useNuxtApp()
    const [data, pref] = await Promise.all([
        $api<AIProvider[]>('/ai-config/providers'),
        $api<UserAIPreference>('/ai-config/me/preferences').catch(() => null),
    ])
    providers.value = data

    const defaultId = pref?.effective_text.model_id ?? null
    const next = pickChatModel(
        allModels.value.map(m => m.id),
        selectedModelId.value ? Number(selectedModelId.value) : null,
        defaultId,
        appliedDefaultId,
    )
    appliedDefaultId = defaultId
    selectedModelId.value = next == null ? '' : next.toString()
}

const initialize = async () => {
    if (isInitialized.value) return
    isInitialized.value = true
    try {
        await Promise.all([refreshModels(), fetchSessions()])
    } catch (e) {
        console.error('Failed to initialize chat', e)
        isInitialized.value = false
    }
}

/** AI 设置（服务商、模型、默认模型）变更后调用；助手未加载过则等下次打开时再取。 */
const notifyAIConfigChanged = () => {
    if (!isInitialized.value) return
    refreshModels().catch(e => console.error('Failed to refresh chat models', e))
}

const open = () => {
    isOpen.value = true
    hasUnread.value = false
    if (isInitialized.value) {
        refreshModels().catch(e => console.error('Failed to refresh chat models', e))
    } else {
        initialize()
    }
}

const close = () => {
    isOpen.value = false
    isExpanded.value = false
}

const toggle = () => {
    if (isOpen.value) close()
    else open()
}

const toggleExpanded = () => {
    isExpanded.value = !isExpanded.value
}

export const useGlobalChat = () => ({
    // UI state
    isOpen,
    isExpanded,
    view,
    isSelectionMode,
    selectedMessageIndices,
    hasUnread,
    isPromptManagerOpen,
    previewImage,
    isPreviewOpen,
    panelWidth,
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
    refreshModels,
    notifyAIConfigChanged,
    open,
    close,
    toggle,
    toggleExpanded,
})
