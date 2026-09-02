<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { Upload, Loader2, FileText, CheckCircle2, AlertCircle, Sparkles, Trash2, Plus, Save, FileCode, Image as ImageIcon } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import TiptapEditor from '@/components/TiptapEditor.vue'
import QuestionListItem from '@/components/QuestionListItem.vue'
import QuestionEditDialog from '@/components/QuestionEditDialog.vue'
import PageHeader from '@/components/PageHeader.vue'
import { toast } from 'vue-sonner'
import { zipFolder } from '@/lib/zipFolder'
import type { KnowledgePoint, Subject, ImportItem } from '@/types'

definePageMeta({
  layout: 'default',
})

// --- Types already defined in @/types ---

// --- State ---
const step = ref<'upload' | 'review' | 'success'>('upload')
const activeTab = ref('docx')
const parseMethod = ref<'ai' | 'structured'>('ai')
const importMode = ref<'extract' | 'solve'>('extract')
const file = ref<File | null>(null)
const folderInput = ref<HTMLInputElement | null>(null)
const markdownContent = ref('')
const pastedImage = ref<string | null>(null)
const isUploading = ref(false)
const isImporting = ref(false)
const error = ref<string | null>(null)
const importList = ref<ImportItem[]>([])
const editingItemId = ref<string | null>(null)
const importedTaskId = ref<number | null>(null)
const uploadedFilePath = ref<string | null>(null)

// Global Settings
const globalSettings = ref({
    subject_id: undefined as number | undefined,
    status: 'pending' as 'draft' | 'pending' | 'published',
    source: '' as string,
})

// Image recognition is AI-only; leave the image tab when switching to structured parsing.
watch(parseMethod, (method) => {
    if (method === 'structured' && activeTab.value === 'image') {
        activeTab.value = 'docx'
    }
})

// --- Data Fetching ---
const { $api } = useNuxtApp()
const { data: subjects } = useAPI<Subject[]>('/subjects')
const { data: knowledgePoints } = useAPI<KnowledgePoint[]>('/knowledge-points', { query: { limit: -1 } })

// Default the import subject to the global subject context (still overridable below).
const { currentSubjectId } = useSubjectContext()
globalSettings.value.subject_id = currentSubjectId.value ?? undefined

// Non-blocking import-readiness checks: (1) embedding configured, (2) this subject's KPs vectorized.
const { user } = useAuth()
const isSuperuser = computed(() => !!user.value?.is_superuser)
const embeddingConfigured = ref(true)
const kpVectorized = ref(true)
const chromaReachable = ref(true)

const fetchImportStatus = async () => {
    try {
        const res = await $api<{ embedding_configured: boolean; chroma_reachable: boolean; kp_total: number; kp_vectorized: boolean }>(
            '/knowledge-points/embedding-status',
            { query: { subject_id: globalSettings.value.subject_id } }
        )
        embeddingConfigured.value = res.embedding_configured
        chromaReachable.value = res.chroma_reachable
        kpVectorized.value = res.kp_vectorized
    } catch {
        embeddingConfigured.value = true
        chromaReachable.value = true
        kpVectorized.value = true
    }
}
onMounted(fetchImportStatus)
watch(() => globalSettings.value.subject_id, fetchImportStatus)

// Filter knowledge points based on selected subject
const filteredKnowledgePoints = computed(() => {
    if (!knowledgePoints.value) return []
    if (!globalSettings.value.subject_id) return []
    return knowledgePoints.value.filter(c => c.subject_id === globalSettings.value.subject_id)
})

// --- Handlers ---

const handleFileChange = (e: Event) => {
    const target = e.target as HTMLInputElement
    if (target.files && target.files.length > 0) {
        file.value = target.files[0]
        // If it's an image, clear pasted image
        if (file.value.type.startsWith('image/')) {
            pastedImage.value = null
        }
        error.value = null
    }
}

const handleFolderChange = async (e: Event) => {
    const target = e.target as HTMLInputElement
    if (!target.files || target.files.length === 0) return
    try {
        pastedImage.value = null
        file.value = await zipFolder(target.files, 'markdown-folder.zip')
        error.value = null
    } catch (err: any) {
        toast.error('打包文件夹失败: ' + (err?.message ?? err))
    } finally {
        target.value = ''
    }
}

const handlePaste = async (e: ClipboardEvent) => {
    const items = e.clipboardData?.items
    if (!items) return

    for (let i = 0; i < items.length; i++) {
        if (items[i].type.indexOf('image') !== -1) {
            const blob = items[i].getAsFile()
            if (blob) {
                file.value = new File([blob], 'pasted-image.png', { type: blob.type })
                // Create preview URL
                pastedImage.value = URL.createObjectURL(blob)
                error.value = null
            }
            break
        }
    }
}

const handleAutoUpload = () => {
    if (!file.value && !pastedImage.value) return;
    if (!globalSettings.value.subject_id) {
        toast.error('请先选择所属学科')
        return
    }
    if (parseMethod.value === 'ai' && embeddingConfigured.value && !chromaReachable.value) {
        if (!confirm('知识点向量库暂时不可达，是否跳过知识点自动匹配继续导入？')) return
    }

    // Auto-detect based on file type or pasted image
    if (pastedImage.value || (file.value && file.value.type.startsWith('image/'))) {
        handleUploadImage();
    } else if (file.value && file.value.name.endsWith('.zip')) {
        handleUploadMarkdownArchive();
    } else if (file.value && file.value.name.endsWith('.md')) {
        handleUploadMarkdown(true);
    } else {
        handleUploadDocx(); // Default to docx
    }
}

const parseOptions = (rawOptions: string[] | null): { label: string, content: string }[] => {
    if (!rawOptions || rawOptions.length === 0) {
        return [
            { label: 'A', content: '' },
            { label: 'B', content: '' },
            { label: 'C', content: '' },
            { label: 'D', content: '' }
        ]
    }
    
    return rawOptions.map((opt, index) => {
        const match = opt.match(/^([A-Z])[\.、\s]\s*(.*)$/)
        if (match) {
            return { label: match[1], content: match[2] }
        }
        const labels = ['A', 'B', 'C', 'D', 'E', 'F', 'G']
        return { label: labels[index] || '?', content: opt }
    })
}

const transformQuestionsData = (questions: any[]) => {
    return questions.map((q: any, index: number) => {
        let q_type: ImportItem['q_type'] = ''
        if (q.q_type) {
            q_type = q.q_type as ImportItem['q_type']
        } else if (q.type === '选择题') {
            q_type = 'single_choice'
        }
        
        const cleanContent = q.content.replace(/^(\d+[\.、\s]\s*|\(\d+\)\s*)/, '')

        // Extract AI suggested tags
        const ai_suggested_tags: Record<string, string[]> = {}
        const tagCategories = ['year', 'source', 'grade', 'semester', 'exam_type', 'feature']
        
        tagCategories.forEach(cat => {
            if (q[cat]) {
                // Ensure it's an array
                const val = q[cat]
                if (Array.isArray(val)) {
                    ai_suggested_tags[cat] = val
                } else if (typeof val === 'string') {
                    ai_suggested_tags[cat] = [val]
                }
            }
        })

        // Handle generic 'tags' field from AI
        if (q.tags && Array.isArray(q.tags) && q.tags.length > 0) {
             // Merge with existing ai_extracted or create new
             const existing = ai_suggested_tags['ai_extracted'] || []
             ai_suggested_tags['ai_extracted'] = [...new Set([...existing, ...q.tags])]
        }

        return {
            id: `temp-${index}`,
            selected: true,
            content: cleanContent,
            q_type: q_type,
            options: (q_type === 'single_choice' || q_type === 'multiple_choice') ? parseOptions(q.options) : [],
            answer: q.answer || '',
            thinking: q.thinking || '',
            analysis: q.analysis || '',
            difficulty: q.difficulty || 1,
            knowledge_point_ids: q.knowledge_point_ids || [],
            ai_suggested_tags,
            warnings: Array.isArray(q.warnings) ? q.warnings : []
        }
    })
}

const handleUploadDocx = async () => {
    if (!file.value) return
    isUploading.value = true
    error.value = null

    const formData = new FormData()
    formData.append('file', file.value)

    try {
        const data = await $api<any>(`/upload/docx?mode=${importMode.value}&method=${parseMethod.value}&subject_id=${globalSettings.value.subject_id}`, {
            method: 'POST',
            body: formData,
        })

        importList.value = transformQuestionsData(data.questions)
        if (data.file_path) {
            uploadedFilePath.value = data.file_path
        }
        step.value = 'review'
    } catch (e: any) {
        error.value = e.message
    } finally {
        isUploading.value = false
    }
}

const handleUploadMarkdown = async (isFile: boolean = false) => {
    if (isFile && !file.value) return
    if (!isFile && !markdownContent.value.trim()) {
        toast.error('请输入 Markdown 内容')
        return
    }

    isUploading.value = true
    error.value = null

    try {
        let data
        if (isFile) {
            const formData = new FormData()
            formData.append('file', file.value!)
            data = await $api<any>(`/upload/markdown?mode=${importMode.value}&method=${parseMethod.value}&subject_id=${globalSettings.value.subject_id}`, {
                method: 'POST',
                body: formData,
            })
        } else {
            data = await $api<any>('/upload/markdown-text', {
                method: 'POST',
                body: { content: markdownContent.value, mode: importMode.value, method: parseMethod.value, subject_id: globalSettings.value.subject_id },
            })
        if (data.file_path) {
            uploadedFilePath.value = data.file_path
        }
        }

        importList.value = transformQuestionsData(data.questions)
        step.value = 'review'
    } catch (e: any) {
        error.value = e.message
    } finally {
        isUploading.value = false
    }
}

const handleUploadMarkdownArchive = async () => {
    if (!file.value) return
    isUploading.value = true
    error.value = null

    const formData = new FormData()
    formData.append('file', file.value)

    try {
        const data = await $api<any>(`/upload/markdown-archive?mode=${importMode.value}&method=${parseMethod.value}&subject_id=${globalSettings.value.subject_id}`, {
            method: 'POST',
            body: formData,
        })

        if (data.file_path) {
            uploadedFilePath.value = data.file_path
        }
        importList.value = transformQuestionsData(data.questions)
        step.value = 'review'
    } catch (e: any) {
        error.value = e.message
    } finally {
        isUploading.value = false
    }
}

const handleUploadImage = async () => {
    if (!file.value) return
    isUploading.value = true
    error.value = null

    const formData = new FormData()
    formData.append('file', file.value)

    try {
        const data = await $api<any>(`/upload/image-recognition?mode=${importMode.value}&subject_id=${globalSettings.value.subject_id}`, {
            method: 'POST',
            body: formData,
        })

        importList.value = transformQuestionsData(data.questions)
        step.value = 'review'
    } catch (e: any) {
        error.value = e.message
    } finally {
        isUploading.value = false
    }
}

const handleImport = async () => {
    if (!globalSettings.value.subject_id) {
        toast.error('请先选择所属学科')
        return
    }

    const selectedItems = importList.value.filter(item => item.selected)
    if (selectedItems.length === 0) {
        toast.error('请至少选择一道题目')
        return
    }

    isImporting.value = true
    try {
        // 智能导入是 legacy 路径：直接发送旧字符串字段，由后端 adapter 统一转 v2，
        // 前端不复制后端答案解析/稳定 id 规则。
        const questions = selectedItems.map(item => ({
            content: item.content,
            q_type: item.q_type,
            options: (item.q_type === 'single_choice' || item.q_type === 'multiple_choice') ? item.options : [],
            answer: item.answer,
            thinking: item.thinking,
            analysis: item.analysis,
            difficulty: item.difficulty,
            knowledge_point_ids: item.knowledge_point_ids,
            tag_ids: [],
            status: globalSettings.value.status,
            subject_id: item.subject_id || globalSettings.value.subject_id,
            ai_suggested_tags: item.ai_suggested_tags,
            source: globalSettings.value.source || undefined
        }))

        const payload = {
            filename: file.value?.name,
            file_path: uploadedFilePath.value,
            questions: questions
        }

        const result = await $api<{
            import_task_id: number | null
            created: { import_task_id?: number }[]
            failed: { index: number, message: string }[]
        }>('/questions/batch-legacy', {
            method: 'POST',
            body: payload
        })

        importedTaskId.value = result.import_task_id

        const createdCount = result.created.length
        if (result.failed.length > 0) {
            toast.warning(`${result.failed.length} 道题目无法解析已跳过，成功导入 ${createdCount} 道`)
        } else {
            toast.success(`成功导入 ${createdCount} 道题目`)
        }
        step.value = 'success'
    } catch (e: any) {
        toast.error('导入失败', { description: e.message })
    } finally {
        isImporting.value = false
    }
}

const removeItem = (index: number) => {
    importList.value.splice(index, 1)
}

const addOption = (item: ImportItem) => {
    const labels = ['A', 'B', 'C', 'D', 'E', 'F', 'G']
    const nextLabel = labels[item.options.length] || '?'
    item.options.push({ label: nextLabel, content: '' })
}

const removeOption = (item: ImportItem, optIndex: number) => {
    item.options.splice(optIndex, 1)
}

const duplicateItem = (index: number) => {
    const item = importList.value[index]
    const newItem = JSON.parse(JSON.stringify(item))
    newItem.id = `temp-${Date.now()}`
    importList.value.splice(index + 1, 0, newItem)
}

const editItem = (id: string) => {
    editingItemId.value = id
}

const handleEditSuccess = (updatedQuestion: ImportItem) => {
    if (editingItemId.value) {
        const index = importList.value.findIndex(i => i.id === editingItemId.value)
        if (index !== -1) {
            importList.value[index] = updatedQuestion
        }
    }
    editingItemId.value = null
}

const getEditingItem = () => {
    return importList.value.find(item => item.id === editingItemId.value)
}

const reset = () => {
    file.value = null
    markdownContent.value = ''
    pastedImage.value = null
    uploadedFilePath.value = null
    importList.value = []
    step.value = 'upload'
    error.value = null
}
</script>

<template>
    <PageHeader title="智能导入" />
    <div class="flex flex-1 flex-col p-4 space-y-6">
        
        <!-- Step 1: Upload -->
        <div v-if="step === 'upload'" class="w-full">
            <div class="space-y-6">
                <Alert v-if="!embeddingConfigured" class="max-w-4xl mx-auto">
                    <AlertCircle class="h-4 w-4" />
                    <AlertDescription>
                        未配置 Embedding 模型，导入时不会自动匹配知识点。可前往
                        <NuxtLink to="/settings" class="underline font-medium">系统设置</NuxtLink>
                        配置后再导入。
                    </AlertDescription>
                </Alert>
                <Alert v-else-if="!kpVectorized" class="max-w-4xl mx-auto">
                    <AlertCircle class="h-4 w-4" />
                    <AlertDescription>
                        <template v-if="isSuperuser">
                            当前学科的知识点尚未建立向量索引，导入时不会自动匹配。可前往
                            <NuxtLink to="/knowledge-points" class="underline font-medium">知识点管理</NuxtLink>
                            重建索引。
                        </template>
                        <template v-else>
                            当前学科的知识点尚未建立向量索引，导入时不会自动匹配，请联系管理员重建索引。
                        </template>
                    </AlertDescription>
                </Alert>
                <!-- Input Source Tabs -->
                <Tabs defaultValue="file" class="w-full max-w-4xl mx-auto">
                    <TabsList class="grid w-full grid-cols-2">
                        <TabsTrigger value="file" class="gap-2">
                            <Upload class="h-4 w-4" />
                            文件或图片
                        </TabsTrigger>
                        <TabsTrigger value="text" class="gap-2">
                            <FileCode class="h-4 w-4" />
                            纯文本粘贴
                        </TabsTrigger>
                    </TabsList>
                    
                    <!-- File Dropzone -->
                    <TabsContent value="file" class="mt-4">
                        <div
                            @dragover.prevent
                            @drop.prevent="handleFileChange"
                            @paste="handlePaste"
                            tabindex="0"
                            class="relative group border-2 border-dashed rounded-xl p-12 text-center transition-all hover:border-primary focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 flex flex-col items-center justify-center min-h-[320px] bg-muted/20"
                            :class="[pastedImage ? 'border-primary bg-primary/5' : 'border-muted-foreground/30 hover:bg-muted/50']"
                        >
                            <input
                                type="file"
                                id="mega-file-upload"
                                class="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
                                accept=".docx,.md,.zip,image/*"
                                @change="handleFileChange"
                                :disabled="isUploading"
                                title="点击上传文件"
                            />
                            
                            <!-- Initial State -->
                            <div v-if="!file && !pastedImage" class="space-y-6 pointer-events-none relative z-0">
                                <div class="bg-background w-20 h-20 rounded-full flex items-center justify-center mx-auto shadow-sm border">
                                    <Upload class="h-10 w-10 text-muted-foreground group-hover:text-primary transition-colors" />
                                </div>
                                <div class="space-y-2">
                                    <h3 class="text-xl font-medium">点击此处 或 拖拽文件到这里上传</h3>
                                    <p class="text-sm text-muted-foreground">同时支持 Ctrl/Cmd + V 直接粘贴屏幕截图</p>
                                </div>
                                <div class="flex items-center justify-center gap-4 text-xs text-muted-foreground mt-4">
                                    <span class="flex items-center gap-1"><FileText class="h-3 w-3"/> Word (.docx)</span>
                                    <span class="flex items-center gap-1"><FileCode class="h-3 w-3"/> Markdown (.md / .zip)</span>
                                    <span class="flex items-center gap-1"><ImageIcon class="h-3 w-3"/> 图片提取</span>
                                </div>
                            </div>
                            
                            <!-- File Selected State -->
                            <div v-else class="space-y-6 relative z-20 w-full max-w-md">
                                <div class="p-6 bg-background rounded-lg shadow-sm border flex flex-col items-center gap-4">
                                    <template v-if="pastedImage">
                                        <img :src="pastedImage" alt="Pasted image" class="max-h-48 rounded border shadow-sm object-contain" />
                                        <div class="text-sm font-medium text-center truncate w-full">已粘贴图片</div>
                                    </template>
                                    <template v-else-if="file">
                                         <div class="h-16 w-16 bg-primary/10 rounded-full flex items-center justify-center">
                                            <ImageIcon v-if="file.type.startsWith('image/')" class="h-8 w-8 text-primary" />
                                            <FileText v-else-if="file.name.endsWith('.docx')" class="h-8 w-8 text-primary" />
                                            <FileCode v-else class="h-8 w-8 text-primary" />
                                         </div>
                                         <div class="text-sm font-medium text-center truncate w-full px-4" :title="file.name">
                                             {{ file.name }}
                                         </div>
                                         <div class="text-xs text-muted-foreground">
                                             {{ (file.size / 1024 / 1024).toFixed(2) }} MB
                                         </div>
                                    </template>
                                    
                                    <div class="mt-2 w-full">
                                        <Button variant="outline" class="w-full" @click.stop="reset" :disabled="isUploading">
                                            <Trash2 class="h-4 w-4 mr-2" />
                                            删除并重新选择
                                        </Button>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <!-- Markdown 含本地图片:上传 .zip 或整个文件夹 -->
                        <div class="mt-3 text-center text-xs text-muted-foreground">
                            Markdown 引用了本地图片？上传 <span class="font-medium">.zip</span> 压缩包，或
                            <button type="button" class="underline hover:text-primary" :disabled="isUploading" @click="folderInput?.click()">选择整个文件夹</button>
                            <input
                                ref="folderInput"
                                type="file"
                                class="hidden"
                                webkitdirectory
                                directory
                                multiple
                                @change="handleFolderChange"
                            />
                        </div>
                    </TabsContent>
                    <TabsContent value="text" class="mt-4">
                        <div class="border rounded-xl bg-background p-4 min-h-[320px] flex flex-col shadow-sm">
                            <TiptapEditor 
                                v-model="markdownContent" 
                                placeholder="将含有题目的文档内容或纯文本直接粘贴到此处..."
                                min-height="min-h-[250px]"
                            />
                        </div>
                    </TabsContent>
                </Tabs>

                <!-- Parsing Settings & Submit -->
                <div class="space-y-6 bg-accent/20 rounded-xl p-6 border max-w-4xl mx-auto w-full">
                    <div>
                        <h3 class="text-lg font-medium mb-4">个性化解析设置</h3>
                        
                        <!-- Primary Parsing Methods -->
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div
                                class="flex items-start space-x-3 border-2 rounded-lg p-4 cursor-pointer transition-all hover:bg-accent/50 bg-background"
                                :class="parseMethod === 'ai' ? 'border-primary ring-1 ring-primary shadow-sm' : 'border-muted'"
                                @click="parseMethod = 'ai'"
                            >
                                <div class="mt-0.5"><CheckCircle2 v-if="parseMethod === 'ai'" class="h-5 w-5 text-primary" /><div v-else class="h-5 w-5 rounded-full border opacity-50"/></div>
                                <div>
                                    <div class="text-base font-medium flex items-center gap-2">
                                        ✨ 强力 AI 识别
                                    </div>
                                    <div class="text-sm text-muted-foreground mt-1">自动识别各种排版或截图题目，无需格式。</div>
                                </div>
                            </div>
                            
                            <div
                                class="flex items-start space-x-3 border-2 rounded-lg p-4 cursor-pointer transition-all hover:bg-accent/50 bg-background"
                                :class="parseMethod === 'structured' ? 'border-primary ring-1 ring-primary shadow-sm' : 'border-muted'"
                                @click="parseMethod = 'structured'"
                            >
                                <div class="mt-0.5"><CheckCircle2 v-if="parseMethod === 'structured'" class="h-5 w-5 text-primary" /><div v-else class="h-5 w-5 rounded-full border opacity-50"/></div>
                                <div>
                                    <div class="text-base font-medium">📝 严格模板解析</div>
                                    <div class="text-sm text-muted-foreground mt-1">适用于已按【题目】【答案】等标签排版好的题库。</div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Dynamic Sub-settings based on parse method -->
                    <div class="pl-4 border-l-2 border-primary/20 space-y-4 pt-2">
                        <!-- AI Sub-settings -->
                        <template v-if="parseMethod === 'ai'">
                            <Label class="text-sm font-medium text-foreground">选择 AI 处理模式</Label>
                            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                <div 
                                    class="flex items-center space-x-3 border rounded-lg p-3 cursor-pointer hover:bg-accent/50 bg-background transition-all"
                                    :class="importMode === 'extract' ? 'border-primary bg-primary/5' : ''"
                                    @click="importMode = 'extract'"
                                >
                                    <div class="h-4 w-4 rounded-full border flex items-center justify-center" :class="importMode === 'extract' ? 'border-primary' : 'border-muted-foreground'">
                                        <div v-if="importMode === 'extract'" class="h-2 w-2 rounded-full bg-primary" />
                                    </div>
                                    <div>
                                        <div class="text-sm font-medium">📥 仅提取/原样录入</div>
                                        <div class="text-xs text-muted-foreground">提取原文件内的题目和答案。</div>
                                    </div>
                                </div>
                                <div 
                                    class="flex items-center space-x-3 border rounded-lg p-3 cursor-pointer hover:bg-accent/50 bg-background transition-all"
                                    :class="importMode === 'solve' ? 'border-primary bg-primary/5' : ''"
                                    @click="importMode = 'solve'"
                                >
                                    <div class="h-4 w-4 rounded-full border flex items-center justify-center" :class="importMode === 'solve' ? 'border-primary' : 'border-muted-foreground'">
                                        <div v-if="importMode === 'solve'" class="h-2 w-2 rounded-full bg-primary" />
                                    </div>
                                    <div>
                                        <div class="text-sm font-medium">🤖 让 AI 帮我解答</div>
                                        <div class="text-xs text-muted-foreground">AI 会自动为您补全标准答案和解析。</div>
                                    </div>
                                </div>
                            </div>
                        </template>
                        
                        <!-- Structured Sub-settings -->
                        <template v-if="parseMethod === 'structured'">
                            <div class="rounded-md bg-background border p-4 text-sm text-muted-foreground flex items-start gap-2">
                                <AlertCircle class="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
                                <div>
                                    <p class="font-medium text-foreground mb-1">模板说明</p>
                                    <p>必须使用 <code class="text-foreground bg-muted px-1.5 py-0.5 rounded text-xs border">【题目】</code> 作为每道题的开头。</p>
                                    <p class="mt-1">非必填标签： <code class="text-foreground bg-muted px-1.5 py-0.5 rounded text-xs border">【选项】</code> <code class="text-foreground bg-muted px-1.5 py-0.5 rounded text-xs border">【答案】</code> <code class="text-foreground bg-muted px-1.5 py-0.5 rounded text-xs border">【解析】</code></p>
                                </div>
                            </div>
                        </template>
                    </div>

                    <!-- Final Action -->
                    <div class="pt-4 mt-4 border-t">
                        <Button 
                            class="w-full text-lg h-14 shadow-lg transition-all" 
                            :class="parseMethod === 'ai' ? 'bg-primary' : 'bg-slate-800 hover:bg-slate-900 dark:bg-slate-700'" 
                            @click="handleAutoUpload" 
                            :disabled="(!file && !pastedImage && !markdownContent.trim()) || isUploading"
                        >
                            <Loader2 v-if="isUploading" class="mr-2 h-6 w-6 animate-spin" />
                            <Sparkles v-else-if="parseMethod === 'ai'" class="mr-2 h-6 w-6" />
                            <FileCode v-else class="mr-2 h-6 w-6" />
                            {{ isUploading ? '正在拼命识别中...' : (parseMethod === 'ai' ? '开始智能识别' : '开始模板解析') }}
                        </Button>
                        <p v-if="(!file && !pastedImage && !markdownContent.trim())" class="text-center text-sm text-destructive mt-3">
                            请在上方提供文件或纯文本内容
                        </p>
                    </div>
                    
                    <!-- Error Box -->
                    <div v-if="error" class="mt-4 p-4 rounded-md bg-destructive/15 text-destructive border border-destructive/20 flex items-center gap-2 text-sm shadow-sm transition-all animate-in fade-in slide-in-from-bottom-2">
                        <AlertCircle class="h-4 w-4 shrink-0" />
                        <span class="break-all">{{ error }}</span>
                    </div>
                </div>
            </div>
        </div>

        <!-- Step 2: Review (unchanged) -->
        <div v-if="step === 'review'" class="space-y-6">
            <!-- Global Settings -->
            <Card class="sticky top-4 z-10 shadow-md border-primary/20">
                <CardHeader class="pb-3">
                    <CardTitle class="text-lg flex items-center justify-between">
                        <span>批量设置</span>
                        <div class="flex items-center gap-2">
                            <Button variant="outline" @click="reset">取消</Button>
                            <Button @click="handleImport" :disabled="isImporting">
                                <Loader2 v-if="isImporting" class="mr-2 h-4 w-4 animate-spin" />
                                <Save v-else class="mr-2 h-4 w-4" />
                                确认导入 ({{ importList.filter(i => i.selected).length }})
                            </Button>
                        </div>
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div class="space-y-2">
                            <Label>初始状态</Label>
                            <Select v-model="globalSettings.status">
                                <SelectTrigger>
                                    <SelectValue placeholder="选择状态" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="draft">草稿 (Draft)</SelectItem>
                                    <SelectItem value="pending">待审核 (Pending)</SelectItem>
                                    <SelectItem value="published">已发布 (Published)</SelectItem>
                                </SelectContent>
                            </Select>
                            <p class="text-xs text-muted-foreground">设置导入题目的初始状态，默认为待审核</p>
                        </div>
                        <div class="space-y-2">
                            <Label>来源 (Source)</Label>
                            <Input v-model="globalSettings.source" placeholder="例如：2023年期末考试" />
                            <p class="text-xs text-muted-foreground">设置导入题目的来源信息</p>
                        </div>
                    </div>
                </CardContent>
            </Card>

            <!-- Question List -->
            <div class="space-y-4">
                <div v-if="importList.length === 0" class="text-center py-8 text-muted-foreground">
                    无导入的题目，请先上传文档或粘贴内容
                </div>

                <QuestionListItem 
                    v-for="(item, index) in importList"
                    :key="item.id"
                    :item="item"
                    :index="index"
                    :all-knowledge-points="knowledgePoints"
                    @edit="editItem(item.id)"
                    @delete="removeItem(index)"
                    @duplicate="duplicateItem(index)"
                />

                <QuestionEditDialog
                    :open="!!editingItemId"
                    :question="getEditingItem()"
                    :knowledge-points="knowledgePoints"
                    :subjects="subjects"
                    :auto-fill-subject-id="globalSettings.subject_id"
                    mode="import"
                    @update:open="(v) => !v && (editingItemId = null)"
                    @save="handleEditSuccess"
                />
            </div>
        </div>

        <!-- Step 3: Success -->
        <div v-if="step === 'success'" class="flex flex-col items-center justify-center py-12 space-y-4">
            <div class="rounded-full bg-green-100 p-3 dark:bg-green-900/20">
                <CheckCircle2 class="h-12 w-12 text-green-600 dark:text-green-400" />
            </div>
            <h2 class="text-2xl font-bold">导入成功</h2>
            <p class="text-muted-foreground">题目已成功添加到题库中。</p>
            <div class="flex gap-4">
                <Button variant="outline" @click="reset">继续导入</Button>
                <Button as-child v-if="importedTaskId">
                    <NuxtLink :to="`/questions?import_task_id=${importedTaskId}`">查看本次导入题目</NuxtLink>
                </Button>
                <Button as-child v-else>
                    <NuxtLink to="/questions">查看题库</NuxtLink>
                </Button>
            </div>
        </div>
    </div>
</template>
