<script setup lang="ts">
import { Send, Bot, User, Loader2, ExternalLink, Image as ImageIcon, X, Trash2, Plus, MessageSquare, Pencil, Book, CheckSquare, Copy } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Checkbox } from '@/components/ui/checkbox'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import ChatMessage from '@/components/ChatMessage.vue'
import PromptManager from '@/components/PromptManager.vue'
import type { AIProvider, AIModel } from '~/types/ai-config'
import { useClipboard } from '@vueuse/core'

definePageMeta({
  layout: 'chat',
  keepalive: true
})

const { $api } = useNuxtApp()
const config = useRuntimeConfig()
const route = useRoute()
const router = useRouter()
const { pendingMessage } = useChatState()

// Types
interface Message {
    id?: number
    role: 'user' | 'assistant' | 'system' | 'tool'
    content: string
    images?: string[]
    tool_calls?: any[]
    actions?: any[]
    proposal?: any
}

interface ChatSession {
    id: string
    title: string
    updated_at: string
}

// State
const sessions = ref<ChatSession[]>([])
const hasMoreSessions = ref(false)
const isLoadingMoreSessions = ref(false)
const SESSION_LIMIT = 20

const editingSessionId = ref<string | null>(null)
const editTitle = ref('')
const editInputRef = ref<HTMLInputElement[] | null>(null)

const currentSessionId = ref<string | null>(null)
const messages = ref<Message[]>([])
const input = ref('')
const selectedImages = ref<string[]>([]) // Previews (DataURL)
const selectedFiles = ref<File[]>([]) // Actual files to upload
const fileInputRef = ref<HTMLInputElement | null>(null)
const loading = ref(false)
const isLoadingMore = ref(false)
const hasMore = ref(false)
const providers = ref<AIProvider[]>([])
const selectedModelId = ref<string>('')
const scrollAreaRef = ref<HTMLElement | null>(null)

// Image Preview State
const previewImage = ref<string | null>(null)
const isPreviewOpen = ref(false)
const isPromptManagerOpen = ref(false)

// Selection Mode State
const isSelectionMode = ref(false)
const selectedMessageIndices = ref<Set<number>>(new Set())
const { copy: copyToClipboard } = useClipboard()

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
}

const copySelectedMessages = () => {
    const selectedIndices = Array.from(selectedMessageIndices.value).sort((a, b) => a - b)
    const selectedMessages = selectedIndices.map(i => messages.value[i])
    
    const text = selectedMessages.map(m => {
        const role = m.role === 'user' ? 'User' : 'Assistant'
        return `**${role}:**\n${m.content}`
    }).join('\n\n---\n\n')
    
    copyToClipboard(text)
    isSelectionMode.value = false
    selectedMessageIndices.value.clear()
}

const openPreview = (img: string) => {
    previewImage.value = img
    isPreviewOpen.value = true
}

const handlePromptSelect = (content: string) => {
    if (input.value) {
        input.value += '\n' + content
    } else {
        input.value = content
    }
}

// Computed
const allModels = computed(() => {
    return providers.value.flatMap(p => p.models.map(m => ({
        ...m,
        providerName: p.name,
        displayName: `${p.name} - ${m.name}`
    })))
})

const currentModel = computed(() => {
    return allModels.value.find(m => m.id.toString() === selectedModelId.value)
})

const isVisionCapable = computed(() => {
    return currentModel.value?.is_vision_capable ?? false
})

// Watch for model changes to clear images if not supported
watch(selectedModelId, () => {
    if (!isVisionCapable.value) {
        selectedImages.value = []
        selectedFiles.value = []
    }
})

// Fetch Data
const fetchSessions = async (loadMore = false) => {
    try {
        if (loadMore) {
            isLoadingMoreSessions.value = true
        }
        
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
        if (loadMore) {
            isLoadingMoreSessions.value = false
        }
    }
}

const loadSession = async (sessionId: string) => {
    try {
        loading.value = true
        messages.value = []
        hasMore.value = false
        currentSessionId.value = sessionId
        // Fetch session info (ignoring messages in the response for now)
        await $api<any>(`/chat/sessions/${sessionId}`)
        
        // Fetch latest messages with pagination
        const msgs = await $api<any[]>(`/chat/sessions/${sessionId}/messages?skip=0&limit=20`)
        
        messages.value = msgs.map((m: any) => ({
            id: m.id,
            role: m.role,
            content: m.content || '',
            images: m.images,
            tool_calls: m.tool_calls
        }))
        
        hasMore.value = msgs.length === 20
        scrollToBottom()
    } catch (e) {
        console.error('Failed to load session', e)
    } finally {
        loading.value = false
    }
}

const loadMore = async () => {
    if (!currentSessionId.value || isLoadingMore.value) return
    
    try {
        isLoadingMore.value = true
        const skip = messages.value.length
        const msgs = await $api<any[]>(`/chat/sessions/${currentSessionId.value}/messages?skip=${skip}&limit=20`)
        
        if (msgs.length < 20) {
            hasMore.value = false
        }
        
        const newMessages = msgs.map((m: any) => ({
            id: m.id,
            role: m.role,
            content: m.content || '',
            images: m.images,
            tool_calls: m.tool_calls
        }))
        
        messages.value = [...newMessages, ...messages.value]
        
    } catch (e) {
        console.error('Failed to load more messages', e)
    } finally {
        isLoadingMore.value = false
    }
}

const createNewSession = () => {
    if (!route.params.id) {
        currentSessionId.value = null
        messages.value = []
        input.value = ''
        selectedImages.value = []
        selectedFiles.value = []
        hasMore.value = false
    } else {
        router.push('/chat')
    }
}

const startEditing = async (session: ChatSession, event: Event) => {
    event.stopPropagation()
    editingSessionId.value = session.id
    editTitle.value = session.title || '新对话'
    await nextTick()
    if (editInputRef.value && editInputRef.value.length > 0) {
        // Since v-for refs are arrays, and we only render one input, it might be the first one or we need to find it.
        // But actually, since we only render ONE input across the whole list (v-if editingSessionId === session.id),
        // the ref array might contain just that one element or we need to be careful.
        // Vue 3 v-for refs are arrays.
        const input = editInputRef.value[0] // It should be the only one rendered if we use the same ref name? 
        // Actually, if we use :ref="(el) => { if(el) editInputRef = el }" on the input, it's easier.
        // Let's just use autofocus on the input, it's simpler.
        input?.focus()
    }
}

const saveTitle = async () => {
    if (!editingSessionId.value) return
    
    const sessionId = editingSessionId.value
    const newTitle = editTitle.value.trim()
    
    // If title is empty or unchanged, just cancel
    const session = sessions.value.find(s => s.id === sessionId)
    if (!newTitle || (session && session.title === newTitle)) {
        editingSessionId.value = null
        return
    }

    try {
        // Optimistic update
        if (session) {
            session.title = newTitle
        }
        
        await $api(`/chat/sessions/${sessionId}`, {
            method: 'PATCH',
            body: { title: newTitle }
        })
    } catch (e) {
        console.error('Failed to update session title', e)
        fetchSessions() // Revert on error
    } finally {
        editingSessionId.value = null
    }
}

const cancelEditing = () => {
    editingSessionId.value = null
}

const handleUpdateMessage = async (event: { id: number, content: string }) => {
    try {
        await $api(`/chat/messages/${event.id}`, {
            method: 'PATCH',
            body: { content: event.content }
        })
        
        // Update local state
        const msg = messages.value.find(m => m.id === event.id)
        if (msg) {
            msg.content = event.content
        }
    } catch (e) {
        console.error('Failed to update message', e)
    }
}

const handleDeleteMessage = async (id: number) => {
    try {
        await $api(`/chat/messages/${id}`, {
            method: 'DELETE'
        })
        
        // Update local state
        messages.value = messages.value.filter(m => m.id !== id)
    } catch (e) {
        console.error('Failed to delete message', e)
    }
}

const deleteSession = async (sessionId: string, event: Event) => {
    event.stopPropagation()
    if (!confirm('确定要删除这个对话吗？')) return
    
    try {
        await $api(`/chat/sessions/${sessionId}`, { method: 'DELETE' })
        sessions.value = sessions.value.filter(s => s.id !== sessionId)
        if (currentSessionId.value === sessionId) {
            createNewSession()
        }
    } catch (e) {
        console.error('Failed to delete session', e)
    }
}

// Watch for route changes to load session
watch(() => route.params.id, async (newId) => {
    const routeId = Array.isArray(newId) ? newId[0] : newId
    
    if (routeId) {
        // Only load if ID changed
        if (String(currentSessionId.value) !== String(routeId)) {
            await loadSession(routeId)
            
            // Check for pending message
            if (pendingMessage.value) {
                input.value = pendingMessage.value.content
                selectedImages.value = pendingMessage.value.images
                selectedFiles.value = pendingMessage.value.files
                selectedModelId.value = pendingMessage.value.modelId
                
                // Clear pending message
                pendingMessage.value = null
                
                // Send message
                await sendMessage()
            }
        }
    } else {
        // Reset for new session
        currentSessionId.value = null
        messages.value = []
        input.value = ''
        selectedImages.value = []
        selectedFiles.value = []
        hasMore.value = false
    }
}, { immediate: true })

onMounted(async () => {
    try {
        const data = await $api<AIProvider[]>('/ai-config/providers')
        providers.value = data
        if (allModels.value.length > 0) {
            selectedModelId.value = allModels.value[0].id.toString()
        }
        await fetchSessions()
    } catch (e) {
        console.error('Failed to fetch providers', e)
    }
})

// Scroll to bottom
const scrollToBottom = async () => {
    await nextTick()
    const scrollContainer = document.querySelector('.chat-scroll-area [data-slot="scroll-area-viewport"]')
    if (scrollContainer) {
        scrollContainer.scrollTop = scrollContainer.scrollHeight
    }
}

// Image handling
const triggerFileInput = () => {
    fileInputRef.value?.click()
}

const handleFileSelect = async (event: Event) => {
    const input = event.target as HTMLInputElement
    if (!input.files?.length) return

    for (const file of Array.from(input.files)) {
        if (file.type.startsWith('image/')) {
            selectedFiles.value.push(file)
            const reader = new FileReader()
            reader.onload = (e) => {
                if (e.target?.result) {
                    selectedImages.value.push(e.target.result as string)
                }
            }
            reader.readAsDataURL(file)
        }
    }
    input.value = ''
}

const handlePaste = (event: ClipboardEvent) => {
    if (!isVisionCapable.value) return

    const items = event.clipboardData?.items
    if (!items) return

    for (const item of Array.from(items)) {
        if (item.type.startsWith('image/')) {
            const file = item.getAsFile()
            if (file) {
                selectedFiles.value.push(file)
                const reader = new FileReader()
                reader.onload = (e) => {
                    if (e.target?.result) {
                        selectedImages.value.push(e.target.result as string)
                    }
                }
                reader.readAsDataURL(file)
            }
        }
    }
}

const removeImage = (index: number) => {
    selectedImages.value.splice(index, 1)
    selectedFiles.value.splice(index, 1)
}

// Send Message
const sendMessage = async () => {
    if ((!input.value.trim() && selectedFiles.value.length === 0) || !selectedModelId.value || loading.value) return

    const userMessageContent = input.value.trim()
    const userImagesPreviews = [...selectedImages.value]
    const userFiles = [...selectedFiles.value]
    
    input.value = ''
    selectedImages.value = []
    selectedFiles.value = []

    // Optimistic update
    // Only do optimistic update if we have a session ID, otherwise we will navigate first
    if (currentSessionId.value) {
        messages.value.push({ 
            role: 'user', 
            content: userMessageContent,
            images: userImagesPreviews.length > 0 ? userImagesPreviews : undefined
        })
        messages.value.push({ role: 'assistant', content: '' })
        loading.value = true
        scrollToBottom()
    }

    try {
        // 1. Create session if needed
        if (!currentSessionId.value) {
            const session = await $api<ChatSession>('/chat/sessions', {
                method: 'POST',
                body: { title: '新对话' }
            })
            
            // Store pending message
            pendingMessage.value = {
                content: userMessageContent,
                images: userImagesPreviews,
                files: userFiles,
                modelId: selectedModelId.value
            }
            
            // Navigate to new session
            await router.push(`/chat/${session.id}`)
            return // Stop execution here, let the new route handle it
        }

        // 2. Upload images
        const uploadedImagePaths: string[] = []
        if (userFiles.length > 0) {
            for (const file of userFiles) {
                const formData = new FormData()
                formData.append('file', file)
                const res = await $api<{url: string}>('/upload/image', {
                    method: 'POST',
                    body: formData
                })
                uploadedImagePaths.push(res.url)
            }
        }

        // 3. Send message
        const token = useCookie('token').value
        const response = await fetch(`/api/v1/chat/sessions/${currentSessionId.value}/messages`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(token ? { 'Authorization': `Bearer ${token}` } : {})
            },
            body: JSON.stringify({
                model_id: parseInt(selectedModelId.value),
                message: {
                    role: 'user',
                    content: userMessageContent,
                    images: uploadedImagePaths.length > 0 ? uploadedImagePaths : undefined
                },
                stream: true
            })
        })

        if (!response.ok) throw new Error(response.statusText)
        if (!response.body) throw new Error('No response body')

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let assistantMessage = ''
        
        // Initialize actions array for the current message
        if (messages.value.length > 0) {
            messages.value[messages.value.length - 1].actions = []
        }

        while (true) {
            const { done, value } = await reader.read()
            if (done) break

            buffer += decoder.decode(value, { stream: true })
            const lines = buffer.split('\n\n')
            buffer = lines.pop() || ''

            for (const line of lines) {
                const eventMatch = line.match(/^event: (.*)$/m)
                const dataMatch = line.match(/^data: (.*)$/m)
                
                if (eventMatch && dataMatch) {
                    const event = eventMatch[1].trim()
                    const dataStr = dataMatch[1].trim()
                    
                    try {
                        const data = JSON.parse(dataStr)
                        
                        // Safety check for messages array
                        if (messages.value.length === 0) continue

                        if (event === 'message') {
                            assistantMessage += data
                            messages.value[messages.value.length - 1].content = assistantMessage
                        } else if (event === 'action') {
                            if (!messages.value[messages.value.length - 1].actions) {
                                messages.value[messages.value.length - 1].actions = []
                            }
                            messages.value[messages.value.length - 1].actions?.push({
                                tool: data.tool,
                                input: data.input,
                                status: 'running'
                            })
                        } else if (event === 'action_result') {
                            const actions = messages.value[messages.value.length - 1].actions
                            if (actions && actions.length > 0) {
                                const lastAction = actions[actions.length - 1]
                                if (lastAction.tool === data.tool) {
                                    lastAction.status = 'completed'
                                    lastAction.output = data.output
                                }
                            }
                        } else if (event === 'proposal') {
                            messages.value[messages.value.length - 1].proposal = data
                        } else if (event === 'message_meta') {
                            // Update message ID
                            if (data.role === 'user') {
                                // The user message is the second to last one (last one is assistant)
                                if (messages.value.length >= 2) {
                                    messages.value[messages.value.length - 2].id = data.id
                                }
                            } else if (data.role === 'assistant') {
                                // The assistant message is the last one
                                if (messages.value.length >= 1) {
                                    messages.value[messages.value.length - 1].id = data.id
                                }
                            }
                        } else if (event === 'done') {
                            // finished
                        }
                        
                        scrollToBottom()
                    } catch (e) {
                        console.error('SSE parse error', e)
                    }
                }
            }
        }
        
        // Refresh sessions to get updated title (after a delay or on next interaction)
        // We can do it silently
        fetchSessions()

    } catch (e) {
        console.error('Chat error', e)
        messages.value[messages.value.length - 1].content += '\n[Error: Failed to generate response]'
    } finally {
        loading.value = false
    }
}
</script>

<template>
    <div class="flex h-full overflow-hidden">
        <!-- Sidebar -->
        <div class="w-64 border-r bg-muted/10 flex flex-col shrink-0">
            <div class="p-4 border-b">
                <Button class="w-full justify-start gap-2" @click="createNewSession">
                    <Plus class="w-4 h-4" />
                    新对话
                </Button>
            </div>
            <ScrollArea class="flex-1 min-h-0">
                <div class="p-2 flex flex-col gap-1">
                    <div 
                        v-for="session in sessions" 
                        :key="session.id"
                        @click="router.push(`/chat/${session.id}`)"
                        :class="[
                            'group flex items-center gap-2 p-2 rounded-md cursor-pointer text-sm hover:bg-accent/50 transition-colors',
                            currentSessionId === session.id ? 'bg-accent text-accent-foreground' : 'text-muted-foreground'
                        ]"
                    >
                        <MessageSquare class="w-4 h-4 shrink-0" />
                        
                        <div v-if="editingSessionId === session.id" class="flex-1 flex items-center min-w-0">
                            <input 
                                v-model="editTitle"
                                class="w-full bg-background border border-input rounded px-2 py-0.5 text-sm h-6 focus:outline-none focus:ring-1 focus:ring-ring"
                                @click.stop
                                @keydown.enter="saveTitle"
                                @keydown.esc="cancelEditing"
                                @blur="saveTitle"
                                ref="editInputRef"
                                autofocus
                            />
                        </div>
                        <span v-else class="truncate flex-1">{{ session.title || '新对话' }}</span>

                        <div v-if="editingSessionId !== session.id" class="flex items-center opacity-0 group-hover:opacity-100 transition-opacity gap-0.5">
                            <button 
                                class="p-1.5 hover:bg-background hover:text-foreground rounded-md transition-colors"
                                @click="(e) => startEditing(session, e)"
                                title="重命名"
                            >
                                <Pencil class="w-3 h-3" />
                            </button>
                            <button 
                                class="p-1.5 hover:bg-destructive/10 hover:text-destructive rounded-md transition-colors"
                                @click="(e) => deleteSession(session.id, e)"
                                title="删除"
                            >
                                <Trash2 class="w-3 h-3" />
                            </button>
                        </div>
                    </div>
                    <Button 
                        v-if="hasMoreSessions" 
                        variant="ghost" 
                        size="sm" 
                        class="w-full text-xs mt-2" 
                        @click="fetchSessions(true)" 
                        :disabled="isLoadingMoreSessions"
                    >
                        <Loader2 v-if="isLoadingMoreSessions" class="w-3 h-3 animate-spin mr-2" />
                        {{ isLoadingMoreSessions ? '加载中...' : '加载更多' }}
                    </Button>
                </div>
            </ScrollArea>
        </div>

        <!-- Main Chat Area -->
        <div class="relative flex flex-1 flex-col min-h-0 overflow-hidden bg-background">
            <PageHeader :title="currentSessionId ? (sessions.find(s => s.id === currentSessionId)?.title || '对话') : '新对话'">
                <template #actions>
                    <div class="flex items-center gap-2">
                        <Button variant="ghost" size="icon" @click="toggleSelectionMode" :class="isSelectionMode ? 'bg-accent' : ''" title="多选消息">
                            <CheckSquare class="w-4 h-4" />
                        </Button>
                        <Select v-model="selectedModelId">
                            <SelectTrigger class="w-[200px]">
                                <SelectValue placeholder="选择模型" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem v-for="model in allModels" :key="model.id" :value="model.id.toString()">
                                    <div class="flex items-center gap-2">
                                        <span>{{ model.displayName }}</span>
                                        <ImageIcon v-if="model.is_vision_capable" class="w-3 h-3 text-muted-foreground" />
                                    </div>
                                </SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                </template>
            </PageHeader>
            
            <div class="flex flex-1 flex-col min-h-0 overflow-hidden">
                <div class="@container/main flex flex-1 flex-col px-4 py-6 gap-6 min-h-0">
                    <!-- Chat Area -->
                    <ScrollArea class="chat-scroll-area flex-1 min-h-0 pr-4">
                        <div class="flex flex-col gap-8">
                            <div v-if="hasMore" class="flex justify-center py-4">
                                <Button variant="ghost" size="sm" @click="loadMore" :disabled="isLoadingMore">
                                    <Loader2 v-if="isLoadingMore" class="w-4 h-4 animate-spin mr-2" />
                                    {{ isLoadingMore ? '加载中...' : '加载更多历史消息' }}
                                </Button>
                            </div>

                            <div v-if="messages.length === 0"
                                class="flex flex-col items-center justify-center h-64 text-muted-foreground">
                                <Bot class="w-12 h-12 mb-4 opacity-20" />
                                <p>开始与 AI 对话吧...</p>
                            </div>
                            <div v-for="(msg, index) in messages" :key="index" class="flex gap-3 items-start">
                                <!-- Selection Checkbox -->
                                <div v-if="isSelectionMode" class="pt-2 shrink-0">
                                    <Checkbox 
                                        :checked="selectedMessageIndices.has(index)"
                                        @update:model-value="toggleMessageSelection(index)"
                                    />
                                </div>

                                <div :class="['flex gap-3 flex-1', msg.role === 'user' ? 'flex-row-reverse' : '']">
                                    <Avatar class="w-8 h-8">
                                        <AvatarFallback
                                            :class="msg.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted'">
                                            <User v-if="msg.role === 'user'" class="w-4 h-4" />
                                            <Bot v-else class="w-4 h-4" />
                                        </AvatarFallback>
                                    </Avatar>

                                    <ChatMessage 
                                        :id="msg.id"
                                        :role="msg.role" 
                                        :content="msg.content" 
                                        :images="msg.images"
                                        :loading="loading && index === messages.length - 1"
                                        :actions="msg.actions"
                                        :proposal="msg.proposal"
                                        @preview-image="openPreview"
                                        @update="handleUpdateMessage"
                                        @delete="handleDeleteMessage"
                                    />
                                </div>
                            </div>
                        </div>
                    </ScrollArea>

                    <!-- Input Area or Selection Bar -->
                    <div v-if="isSelectionMode" class="p-4 border-t shrink-0 flex items-center justify-center gap-4 bg-background animate-in fade-in slide-in-from-bottom-4">
                        <span class="text-sm font-medium">已选择 {{ selectedMessageIndices.size }} 条消息</span>
                        <div class="h-4 w-px bg-border"></div>
                        <Button size="sm" @click="copySelectedMessages" :disabled="selectedMessageIndices.size === 0">
                            <Copy class="w-4 h-4 mr-2" />
                            复制 Markdown
                        </Button>
                        <Button size="sm" variant="ghost" @click="toggleSelectionMode">
                            <X class="w-4 h-4 mr-2" />
                            取消
                        </Button>
                    </div>

                    <div v-else class="pt-4 border-t shrink-0">
                        <!-- Image Preview -->
                        <div v-if="selectedImages.length > 0" class="flex gap-2 mb-2 overflow-x-auto pt-3 pb-2 px-2">
                            <div v-for="(img, index) in selectedImages" :key="index" class="relative shrink-0">
                                <img 
                                    :src="img" 
                                    class="h-20 w-20 object-cover rounded-md border cursor-pointer hover:opacity-90 transition-opacity" 
                                    @click="openPreview(img)"
                                />
                                <button @click="removeImage(index)" type="button" class="absolute -top-2 -right-2 bg-destructive text-destructive-foreground rounded-full p-0.5 hover:bg-destructive/90">
                                    <X class="w-3 h-3" />
                                </button>
                            </div>
                        </div>

                        <form @submit.prevent="sendMessage" class="flex gap-2 items-end">
                            <input type="file" ref="fileInputRef" multiple accept="image/*" class="hidden" @change="handleFileSelect" />
                            
                            <Button v-if="isVisionCapable" type="button" variant="outline" size="icon" @click="triggerFileInput" title="上传图片">
                                <ImageIcon class="w-4 h-4" />
                            </Button>

                            <Button type="button" variant="outline" size="icon" @click="isPromptManagerOpen = true" title="常用指令">
                                <Book class="w-4 h-4" />
                            </Button>

                            <Textarea v-model="input" :placeholder="isVisionCapable ? '输入消息... (支持粘贴图片)' : '输入消息...'" class="min-h-[50px] max-h-[200px]"
                                @keydown.enter="(e) => { if (!e.shiftKey) { e.preventDefault(); sendMessage() } }" 
                                @paste="handlePaste"
                            />
                            <Button type="submit" :disabled="loading || (!input.trim() && selectedImages.length === 0) || !selectedModelId">
                                <Loader2 v-if="loading" class="w-4 h-4 animate-spin" />
                                <Send v-else class="w-4 h-4" />
                            </Button>
                        </form>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <Dialog v-model:open="isPreviewOpen">
        <DialogContent class="max-w-4xl w-full p-0 overflow-hidden bg-transparent border-none shadow-none sm:max-w-4xl">
            <div class="relative flex items-center justify-center w-full h-full" @click="isPreviewOpen = false">
                <img v-if="previewImage" :src="previewImage" class="max-w-full max-h-[90vh] object-contain rounded-md" />
            </div>
        </DialogContent>
    </Dialog>

    <PromptManager 
        v-model:open="isPromptManagerOpen" 
        @select="handlePromptSelect" 
    />
</template>
