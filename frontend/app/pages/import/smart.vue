<script setup lang="ts">
import { ref, computed } from 'vue'
import { Upload, Loader2, FileText, CheckCircle2, AlertCircle, Sparkles, Trash2, Plus, Save, FileCode, Image as ImageIcon } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
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
import type { KnowledgePoint, Subject, ImportItem } from '@/types'

definePageMeta({
  layout: 'default',
})

// --- Types already defined in @/types ---

// --- State ---
const step = ref<'upload' | 'review' | 'success'>('upload')
const activeTab = ref('docx')
const importMode = ref<'extract' | 'solve'>('extract')
const file = ref<File | null>(null)
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

// --- Data Fetching ---
const { $api } = useNuxtApp()
const { data: subjects } = useAPI<Subject[]>('/subjects')
const { data: knowledgePoints } = useAPI<KnowledgePoint[]>('/knowledge-points', { query: { limit: -1 } })

// Fetch current user and auto-fill subject_id
const { data: currentUser } = await useAPI('/users/me')
if ((currentUser.value as any)?.subject_id) {
    globalSettings.value.subject_id = (currentUser.value as any).subject_id
}

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
            options: q_type === 'single_choice' ? parseOptions(q.options) : [],
            answer: q.answer || '',
            thinking: q.thinking || '',
            analysis: q.analysis || '',
            difficulty: q.difficulty || 1,
            knowledge_point_ids: q.knowledge_point_ids || [],
            ai_suggested_tags
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
        const data = await $api<any>(`/upload/docx?mode=${importMode.value}`, {
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
            data = await $api<any>(`/upload/markdown?mode=${importMode.value}`, {
                method: 'POST',
                body: formData,
            })
        } else {
            data = await $api<any>('/upload/markdown-text', {
                method: 'POST',
                body: { content: markdownContent.value, mode: importMode.value },
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

const handleUploadImage = async () => {
    if (!file.value) return
    isUploading.value = true
    error.value = null

    const formData = new FormData()
    formData.append('file', file.value)

    try {
        const data = await $api<any>(`/upload/image-recognition?mode=${importMode.value}`, {
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
        const questions = selectedItems.map(item => ({
            content: item.content,
            q_type: item.q_type,
            options: (item.q_type === 'single_choice' || item.q_type === 'multiple_choice') ? item.options : [],
            answer: (typeof item.answer === 'object' && item.answer !== null) ? JSON.stringify(item.answer) : item.answer,
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

        const createdQuestions = await $api<any[]>('/questions/batch', {
            method: 'POST',
            body: payload
        })

        if (createdQuestions && createdQuestions.length > 0) {
            importedTaskId.value = createdQuestions[0].import_task_id
        }

        toast.success(`成功导入 ${selectedItems.length} 道题目`)
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
        <div v-if="step === 'upload'" class="max-w-4xl mx-auto w-full">
            <Card>
                <CardHeader>
                    <CardTitle class="flex items-center gap-2">
                        <Sparkles class="h-5 w-5" />
                        选择识别方式
                    </CardTitle>
                    <CardDescription>
                        支持多种方式导入题目，AI 将自动提取题目、选项、答案和解析。
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <div class="mb-6">
                        <Label class="text-base font-medium mb-2 block">处理模式</Label>
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div 
                                class="flex items-start space-x-3 border rounded-lg p-4 cursor-pointer transition-all hover:border-primary/50"
                                :class="{ 'bg-accent/50 border-primary ring-1 ring-primary': importMode === 'extract' }"
                                @click="importMode = 'extract'"
                            >
                                <div class="mt-1 h-4 w-4 rounded-full border border-primary flex items-center justify-center shrink-0">
                                    <div v-if="importMode === 'extract'" class="h-2 w-2 rounded-full bg-primary" />
                                </div>
                                <div>
                                    <div class="font-medium">录入原题</div>
                                    <div class="text-sm text-muted-foreground mt-1">提取文档中的题目、答案和解析，保持原样。适用于已有标准答案的题。</div>
                                </div>
                            </div>
                            <div 
                                class="flex items-start space-x-3 border rounded-lg p-4 cursor-pointer transition-all hover:border-primary/50"
                                :class="{ 'bg-accent/50 border-primary ring-1 ring-primary': importMode === 'solve' }"
                                @click="importMode = 'solve'"
                            >
                                <div class="mt-1 h-4 w-4 rounded-full border border-primary flex items-center justify-center shrink-0">
                                    <div v-if="importMode === 'solve'" class="h-2 w-2 rounded-full bg-primary" />
                                </div>
                                <div>
                                    <div class="font-medium flex items-center gap-2">
                                        AI 自动做题
                                        <Sparkles class="h-3 w-3 text-amber-500" />
                                    </div>
                                    <div class="text-sm text-muted-foreground mt-1">AI 提取题目并做题并生成标准答案和解析，适用于无答案的教材题。</div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <Tabs v-model="activeTab" class="w-full">
                        <TabsList class="grid w-full grid-cols-3">
                            <TabsTrigger value="docx" class="gap-2">
                                <FileText class="h-4 w-4" />
                                Word 文档
                            </TabsTrigger>
                            <TabsTrigger value="markdown" class="gap-2">
                                <FileCode class="h-4 w-4" />
                                Markdown
                            </TabsTrigger>
                            <TabsTrigger value="image" class="gap-2">
                                <ImageIcon class="h-4 w-4" />
                                图片识别
                            </TabsTrigger>
                        </TabsList>
                        
                        <!-- DOCX Tab -->
                        <TabsContent value="docx" class="space-y-4 mt-4">
                            <div class="space-y-2">
                                <Label for="docx-file">选择 Word 文档</Label>
                                <div class="flex gap-2">
                                    <Input id="docx-file" type="file" accept=".docx" @change="handleFileChange" />
                                    <Button @click="handleUploadDocx" :disabled="!file || isUploading">
                                        <Loader2 v-if="isUploading" class="mr-2 h-4 w-4 animate-spin" />
                                        <Upload v-else class="mr-2 h-4 w-4" />
                                        开始识别
                                    </Button>
                                </div>
                                <p class="text-sm text-muted-foreground">
                                    支持 .docx 格式，会自动提取文档中的图片和数学公式。
                                </p>
                            </div>
                        </TabsContent>

                        <!-- Markdown Tab -->
                        <TabsContent value="markdown" class="space-y-4 mt-4">
                            <div class="space-y-4">
                                <!-- File Upload -->
                                <div class="space-y-2">
                                    <Label for="md-file">方式一：上传 Markdown 文件</Label>
                                    <div class="flex gap-2">
                                        <Input id="md-file" type="file" accept=".md" @change="handleFileChange" />
                                        <Button @click="() => handleUploadMarkdown(true)" :disabled="!file || isUploading">
                                            <Loader2 v-if="isUploading" class="mr-2 h-4 w-4 animate-spin" />
                                            <Upload v-else class="mr-2 h-4 w-4" />
                                            识别
                                        </Button>
                                    </div>
                                </div>

                                <div class="relative">
                                    <div class="absolute inset-0 flex items-center">
                                        <span class="w-full border-t" />
                                    </div>
                                    <div class="relative flex justify-center text-xs uppercase">
                                        <span class="bg-background px-2 text-muted-foreground">或</span>
                                    </div>
                                </div>

                                <!-- Direct Input -->
                                <div class="space-y-2">
                                    <Label for="md-content">方式二：直接输入 Markdown 内容</Label>
                                    <TiptapEditor 
                                        v-model="markdownContent" 
                                        placeholder="粘贴或输入 Markdown 格式的题目内容..."
                                        min-height="min-h-[300px]"
                                    />
                                    <Button @click="() => handleUploadMarkdown(false)" :disabled="!markdownContent.trim() || isUploading" class="w-full">
                                        <Loader2 v-if="isUploading" class="mr-2 h-4 w-4 animate-spin" />
                                        <Sparkles v-else class="mr-2 h-4 w-4" />
                                        开始识别
                                    </Button>
                                </div>
                            </div>
                        </TabsContent>

                        <!-- Image Tab -->
                        <TabsContent value="image" class="space-y-4 mt-4">
                            <div class="space-y-4">
                                <!-- File Upload -->
                                <div class="space-y-2">
                                    <Label for="image-file">方式一：选择图片文件</Label>
                                    <div class="flex gap-2">
                                        <Input id="image-file" type="file" accept="image/*" @change="handleFileChange" />
                                    </div>
                                </div>

                                <div class="relative">
                                    <div class="absolute inset-0 flex items-center">
                                        <span class="w-full border-t" />
                                    </div>
                                    <div class="relative flex justify-center text-xs uppercase">
                                        <span class="bg-background px-2 text-muted-foreground">或</span>
                                    </div>
                                </div>

                                <!-- Paste Area -->
                                <div class="space-y-2">
                                    <Label>方式二：粘贴图片 (Ctrl/Cmd + V)</Label>
                                    <div
                                        @paste="handlePaste"
                                        tabindex="0"
                                        class="border-2 border-dashed rounded-lg p-8 text-center cursor-pointer hover:border-primary transition-colors focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2"
                                        :class="pastedImage ? 'border-primary bg-primary/5' : 'border-muted-foreground/25'"
                                    >
                                        <div v-if="!pastedImage" class="space-y-2">
                                            <ImageIcon class="h-12 w-12 mx-auto text-muted-foreground" />
                                            <p class="text-sm text-muted-foreground">点击此处并按 Ctrl/Cmd + V 粘贴图片</p>
                                        </div>
                                        <div v-else class="space-y-2">
                                            <img :src="pastedImage" alt="Pasted image" class="max-h-64 mx-auto rounded" />
                                            <p class="text-sm text-muted-foreground">已粘贴图片</p>
                                        </div>
                                    </div>
                                </div>

                                <Button @click="handleUploadImage" :disabled="!file || isUploading" class="w-full">
                                    <Loader2 v-if="isUploading" class="mr-2 h-4 w-4 animate-spin" />
                                    <Upload v-else class="mr-2 h-4 w-4" />
                                    开始识别
                                </Button>

                                <p class="text-sm text-muted-foreground">
                                    支持 JPG、PNG 等图片格式，使用 AI 视觉模型识别图片中的题目。
                                </p>
                            </div>
                        </TabsContent>
                    </Tabs>

                    <div v-if="error"
                        class="mt-4 p-4 rounded-md bg-destructive/15 text-destructive flex items-center gap-2">
                        <AlertCircle class="h-4 w-4" />
                        <span>{{ error }}</span>
                    </div>
                </CardContent>
            </Card>
        </div>

        <!-- Step 2: Review -->
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
                    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div class="space-y-2">
                            <Label>所属学科 <span class="text-destructive">*</span></Label>
                            <Select v-model="globalSettings.subject_id">
                                <SelectTrigger>
                                    <SelectValue placeholder="选择学科" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem v-for="s in subjects" :key="s.id" :value="s.id">
                                        {{ s.name }}
                                    </SelectItem>
                                </SelectContent>
                            </Select>
                            <p class="text-xs text-muted-foreground">用于过滤可用的分类，每个题目可单独分配分类</p>
                        </div>
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
