<script setup lang="ts">
import { Copy, Check, ExternalLink, Image as ImageIcon, FileDown, Loader2, Pencil, Trash2, X, Save } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import MarkdownPreview from '@/components/MarkdownPreview.vue'
import SvgRenderer from '@/components/SvgRenderer.vue'
import BatchImportCard from '@/components/BatchImportCard.vue'
import { useClipboard } from '@vueuse/core'

interface Action {
    tool: string
    input: any
    output?: string
    status: 'running' | 'completed' | 'error'
}

interface Proposal {
    type: 'single' | 'batch'
    ids: number[]
}

interface Props {
    id?: number
    role: 'user' | 'assistant' | 'system'
    content: string
    images?: string[]
    loading?: boolean
    actions?: Action[]
    proposal?: Proposal
}

const props = defineProps<Props>()
const emit = defineEmits(['preview-image', 'update', 'delete'])

const { copy, copied } = useClipboard()
const exporting = ref(false)
const { $api } = useNuxtApp()

const isEditing = ref(false)
const editContent = ref('')

const startEditing = () => {
    editContent.value = props.content
    isEditing.value = true
}

const cancelEditing = () => {
    isEditing.value = false
    editContent.value = ''
}

const saveEdit = () => {
    if (editContent.value.trim() !== props.content) {
        emit('update', { id: props.id, content: editContent.value })
    }
    isEditing.value = false
}

const deleteMessage = () => {
    if (confirm('确定要删除这条消息吗？')) {
        emit('delete', props.id)
    }
}

const generateFilename = (content: string) => {
    // Try to find first heading or first line
    let title = 'export'
    const headingMatch = content.match(/^#+\s+(.+)$/m)
    if (headingMatch) {
        title = headingMatch[1].trim()
    } else {
        const firstLine = content.split('\n').find(line => line.trim().length > 0)
        if (firstLine) title = firstLine.trim()
    }

    // Truncate and sanitize
    // Keep Chinese characters, letters, numbers, underscores, hyphens
    title = title.slice(0, 30).replace(/[^\w\u4e00-\u9fa5\-_]/g, '_')
    if (!title) title = 'export'
    
    const now = new Date()
    const timestamp = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}_${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}`
    
    return `${title}_${timestamp}.docx`
}

const exportDocx = async () => {
    if (exporting.value) return
    exporting.value = true
    const filename = generateFilename(props.content)

    try {
        const blob = await $api('/tools/md2docx', {
            method: 'POST',
            body: { 
                content: props.content,
                filename: filename
            },
            responseType: 'blob'
        })
        
        const url = window.URL.createObjectURL(blob as Blob)
        const a = document.createElement('a')
        a.href = url
        a.download = filename
        document.body.appendChild(a)
        a.click()
        window.URL.revokeObjectURL(url)
        document.body.removeChild(a)
    } catch (e) {
        console.error('Export failed', e)
    } finally {
        exporting.value = false
    }
}

// Helper to parse message content for question links
const parseMessage = (content: string) => {
    const linkRegex = /\[QUESTION_LINK:(\d+)\]/g
    const confirmRegex = /\[CONFIRM_IMPORT:(\d+)\]/g
    const batchConfirmRegex = /\[CONFIRM_IMPORT_BATCH:([\d,]+)\]/g
    
    let text = content
    const questionIds: string[] = []
    const confirmIds: number[] = []
    const batchConfirmIds: number[] = []

    // Parse QUESTION_LINK
    const linkMatches = [...content.matchAll(linkRegex)]
    if (linkMatches.length > 0) {
        text = text.replace(linkRegex, '')
        linkMatches.forEach(m => questionIds.push(m[1]))
    }

    // Parse CONFIRM_IMPORT
    const confirmMatches = [...content.matchAll(confirmRegex)]
    if (confirmMatches.length > 0) {
        text = text.replace(confirmRegex, '')
        confirmMatches.forEach(m => confirmIds.push(parseInt(m[1])))
    }

    // Parse CONFIRM_IMPORT_BATCH
    const batchMatches = [...content.matchAll(batchConfirmRegex)]
    if (batchMatches.length > 0) {
        text = text.replace(batchConfirmRegex, '')
        batchMatches.forEach(m => {
            const ids = m[1].split(',').map(id => parseInt(id.trim()))
            batchConfirmIds.push(...ids)
        })
    }

    return {
        text,
        questionIds,
        confirmIds,
        batchConfirmIds
    }
}

const parsedContent = computed(() => parseMessage(props.content))

const parts = computed(() => {
    const text = parsedContent.value.text
    // Regex to match SVG code blocks: ```xml <svg ... </svg> ``` or ```svg <svg ... </svg> ```
    // Also handles cases where language might be omitted but it's a code block with svg
    const regex = /```(?:xml|svg)?\s*(<svg[\s\S]*?<\/svg>)\s*```/gi
    const result = []
    let lastIndex = 0
    let match
    
    while ((match = regex.exec(text)) !== null) {
        // Add text before the match
        if (match.index > lastIndex) {
            result.push({ type: 'text', content: text.slice(lastIndex, match.index) })
        }
        
        // Add the SVG
        result.push({ type: 'svg', content: match[1] })
        
        lastIndex = regex.lastIndex
    }
    
    // Add remaining text
    if (lastIndex < text.length) {
        result.push({ type: 'text', content: text.slice(lastIndex) })
    }
    
    return result
})

const copyContent = () => {
    copy(props.content)
}
</script>

<template>
    <div :class="[
        'group relative px-4 py-2 rounded-lg max-w-[80%] text-sm',
        role === 'user'
            ? 'bg-primary text-primary-foreground'
            : 'bg-muted border'
    ]">
        <!-- Images -->
        <div v-if="images && images.length" class="flex flex-wrap gap-2 mb-2">
            <img 
                v-for="(img, i) in images" 
                :key="i" 
                :src="img" 
                class="max-w-[200px] max-h-[200px] rounded-md object-cover bg-background cursor-pointer hover:opacity-90 transition-opacity" 
                @click="$emit('preview-image', img)"
            />
        </div>

        <!-- Actions Log -->
        <div v-if="actions && actions.length" class="mb-2 space-y-1 max-w-full">
            <div v-for="(action, i) in actions" :key="i" class="text-xs bg-background/50 p-2 rounded border w-full overflow-hidden">
                <div class="flex items-center gap-2">
                    <Loader2 v-if="action.status === 'running'" class="w-3 h-3 animate-spin" />
                    <Check v-else-if="action.status === 'completed'" class="w-3 h-3 text-green-500" />
                    <span class="font-mono font-bold truncate">{{ action.tool }}</span>
                </div>
                <div class="text-muted-foreground mt-1 truncate" :title="JSON.stringify(action.input)">
                    Input: {{ JSON.stringify(action.input) }}
                </div>
                <div v-if="action.output" class="text-muted-foreground mt-1 truncate" :title="action.output">
                    Output: {{ action.output }}
                </div>
            </div>
        </div>

        <!-- Content -->
        <div v-if="isEditing" class="min-w-[300px]">
            <Textarea v-model="editContent" class="min-h-[100px] mb-2 bg-background text-foreground" />
            <div class="flex justify-end gap-2">
                <Button size="sm" variant="ghost" @click="cancelEditing">
                    <X class="w-4 h-4 mr-1" /> 取消
                </Button>
                <Button size="sm" @click="saveEdit">
                    <Save class="w-4 h-4 mr-1" /> 保存
                </Button>
            </div>
        </div>
        <div v-else-if="role === 'user'" class="whitespace-pre-wrap break-words overflow-x-auto">
            {{ content }}
        </div>
        <div v-else class="overflow-x-auto">
            <template v-for="(part, index) in parts" :key="index">
                <MarkdownPreview v-if="part.type === 'text'" :content="part.content" />
                <SvgRenderer v-else :code="part.content" />
            </template>
            
            <!-- Question Link -->
            <div v-if="parsedContent.questionIds && parsedContent.questionIds.length" class="mt-2 flex flex-wrap gap-2">
                <Button v-for="qid in parsedContent.questionIds" :key="qid" variant="outline" size="sm" as-child>
                    <NuxtLink :to="`/questions?id=${qid}`" target="_blank">
                        <ExternalLink class="w-4 h-4 mr-2" />
                        查看题目 {{ qid }}
                    </NuxtLink>
                </Button>
            </div>

            <!-- Confirmation Cards -->
            <div v-if="proposal">
                <BatchImportCard :question-ids="proposal.ids" />
            </div>
            <div v-if="parsedContent.confirmIds && parsedContent.confirmIds.length">
                <BatchImportCard :question-ids="parsedContent.confirmIds" />
            </div>
            <div v-if="parsedContent.batchConfirmIds && parsedContent.batchConfirmIds.length">
                <BatchImportCard :question-ids="parsedContent.batchConfirmIds" />
            </div>
        </div>

        <!-- Loading Indicator -->
        <div v-if="loading && !content" class="flex items-center justify-center h-8 w-12">
            <div class="relative w-6 h-6">
                <div class="absolute inset-0 border-2 border-primary/30 rounded-full animate-[ping_2s_cubic-bezier(0,0,0.2,1)_infinite]"></div>
                <div class="absolute inset-0 border-2 border-primary/50 rounded-full animate-[spin_3s_linear_infinite]"></div>
                <div class="absolute inset-1.5 bg-primary rounded-full animate-pulse"></div>
            </div>
        </div>

        <!-- Actions (Copy, Edit, Delete) -->
        <div v-if="!loading && !isEditing" class="absolute -bottom-6 right-0 opacity-0 group-hover:opacity-100 transition-opacity flex gap-1">
            <template v-if="role === 'assistant'">
                <Button variant="ghost" size="icon" class="h-6 w-6" @click="exportDocx" title="导出 Docx" :disabled="exporting">
                    <Loader2 v-if="exporting" class="w-3 h-3 animate-spin" />
                    <FileDown v-else class="w-3 h-3 text-muted-foreground" />
                </Button>
            </template>
            <Button variant="ghost" size="icon" class="h-6 w-6" @click="copyContent" title="复制 Markdown">
                    <Check v-if="copied" class="w-3 h-3 text-green-500" />
                    <Copy v-else class="w-3 h-3 text-muted-foreground" />
                </Button>
            
            <!-- Edit/Delete for both user and assistant -->
            <Button v-if="id" variant="ghost" size="icon" class="h-6 w-6" @click="startEditing" title="编辑">
                <Pencil class="w-3 h-3 text-muted-foreground" />
            </Button>
            <Button v-if="id" variant="ghost" size="icon" class="h-6 w-6" @click="deleteMessage" title="删除">
                <Trash2 class="w-3 h-3 text-muted-foreground hover:text-destructive" />
            </Button>
        </div>
    </div>
</template>
