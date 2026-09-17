<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { Upload, Loader2, FileText, CheckCircle2, AlertCircle, Sparkles, Trash2, Plus, Save, FileCode, Image as ImageIcon } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
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
import { Textarea } from '@/components/ui/textarea'
import QuestionListItem from '@/components/QuestionListItem.vue'
import QuestionEditDialog from '@/components/QuestionEditDialog.vue'
import PageHeader from '@/components/PageHeader.vue'
import { toast } from 'vue-sonner'
import { zipFolder } from '@/lib/zipFolder'
import type { CompositionFolder, CompositionScope, KnowledgePoint, Subject } from '@/types'
import { buildFolderTree } from '@/lib/compositions'
import {
    buildSubmitOutline,
    hasPaperStructure,
    insertQuestionRefAfter,
    type PaperExtraction,
} from '@/lib/paperOutline'
import {
    type ImportDraft,
    type ExtractedQuestionItem,
    extractedItemToDraft,
    buildQuestionPayload,
    generateTempId,
} from '@/lib/questionModel'

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
const importList = ref<ImportDraft[]>([])
const editingItemId = ref<string | null>(null)
const importedTaskId = ref<number | null>(null)
const uploadedFilePath = ref<string | null>(null)

// --- 整卷结构与稿件选项 ---
const paper = ref<PaperExtraction | null>(null)
const contentSha256 = ref<string | null>(null)
const duplicateOf = ref<{ import_task_id: number; original_filename: string | null; imported_at: string | null; composition_id: number | null } | null>(null)

// 默认关闭：只有用户主动勾选才会建稿。
const saveAsComposition = ref(false)
const compositionScope = ref<CompositionScope>('personal')
const compositionTitle = ref('')
const compositionFolderId = ref<number | null>(null)
const renumber = ref(true)
const folders = ref<CompositionFolder[]>([])
const createdComposition = ref<{ id: number; title: string } | null>(null)
const importSkipped = ref<{ temp_id: string | null; message: string }[]>([])
const importDegraded = ref<{ reason: string; excerpt: string }[]>([])
const idempotencyKey = ref<string | null>(null)
const partialFailureDetail = ref<string | null>(null)

const folderOptions = computed(() => {
    const tree = buildFolderTree(folders.value)
    const flat: { id: number; label: string }[] = []
    const walk = (nodes: typeof tree, depth: number) => {
        for (const node of nodes) {
            flat.push({ id: node.id, label: `${'　'.repeat(depth)}${node.name}` })
            walk(node.children, depth + 1)
        }
    }
    walk(tree, 0)
    return flat
})

const hasStructure = computed(() => hasPaperStructure(paper.value))

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

// /upload/* 已返回可编辑的 v2 抽取项（后端清洗+转换），前端直接映射为草稿。
const toDrafts = (items: ExtractedQuestionItem[] | undefined | null): ImportDraft[] =>
    (items ?? []).map((it) => extractedItemToDraft(it, { subjectId: globalSettings.value.subject_id }))

/** 接收一次抽取结果：题目、整卷结构、文件指纹与重复提示。 */
const acceptExtraction = (data: any) => {
    importList.value = toDrafts(data.questions)
    paper.value = data.paper ?? null
    contentSha256.value = data.content_sha256 ?? null
    duplicateOf.value = data.duplicate_of ?? null
    if (data.file_path) uploadedFilePath.value = data.file_path
    compositionTitle.value = (paper.value?.suggested_title || file.value?.name || '').replace(/\.[^.]+$/, '')
    step.value = 'review'
}

const loadFolders = async () => {
    if (!globalSettings.value.subject_id) return
    try {
        folders.value = await $api<CompositionFolder[]>(
            `/subjects/${globalSettings.value.subject_id}/folders`,
            { query: { scope: compositionScope.value } },
        )
    } catch {
        folders.value = []
    }
}

// 切换空间会换一棵目录树，已选目录必须重置。
watch(compositionScope, () => {
    compositionFolderId.value = null
    loadFolders()
})
watch(saveAsComposition, (on) => {
    if (on) loadFolders()
})


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

        acceptExtraction(data)
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
        }

        acceptExtraction(data)
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

        acceptExtraction(data)
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

        acceptExtraction(data)
    } catch (e: any) {
        error.value = e.message
    } finally {
        isUploading.value = false
    }
}

// 抽取结果由 /upload/* 直接返回 v2 草稿项，无需再单独转换。


const handleImport = async (proceedWithPartial = false) => {
    if (!globalSettings.value.subject_id) {
        toast.error('请先选择所属学科')
        return
    }

    const selectedItems = importList.value.filter(item => item.selected)
    if (selectedItems.length === 0) {
        toast.error('请至少选择一道题目')
        return
    }
    if (saveAsComposition.value && !compositionTitle.value.trim()) {
        toast.error('请填写稿件名称')
        return
    }

    isImporting.value = true
    try {
        // 逐条应用全局设置；缺答案的题降级为草稿（与后端 adapter 对齐）。
        const payloadQuestions = selectedItems.map((item) => {
            const d: ImportDraft = JSON.parse(JSON.stringify(item))
            d.subject_id = d.subject_id || globalSettings.value.subject_id
            d.source = globalSettings.value.source || ''
            d.status = d.answer ? globalSettings.value.status : 'draft'
            return {
                ...buildQuestionPayload(d),
                ai_suggested_tags: d.ai_suggested_tags,
                temp_id: d.temp_id,
                parent_temp_id: d.parent_temp_id,
            }
        })

        // 幂等键绑定本次提交：网络重试不会重复建题建稿。
        idempotencyKey.value ||= generateTempId()

        const body = {
            scope: compositionScope.value,
            questions: payloadQuestions,
            outline: buildSubmitOutline(paper.value, selectedItems),
            save_as_composition: saveAsComposition.value,
            title: compositionTitle.value.trim() || null,
            folder_id: compositionFolderId.value,
            renumber: renumber.value,
            proceed_with_partial: proceedWithPartial,
            status: globalSettings.value.status,
            filename: file.value?.name ?? null,
            file_path: uploadedFilePath.value,
            content_sha256: contentSha256.value,
            idempotency_key: idempotencyKey.value,
        }

        const res = await $api<any>(
            `/subjects/${globalSettings.value.subject_id}/paper-imports`,
            { method: 'POST', body },
        )

        importedTaskId.value = res.import_task_id ?? null
        importSkipped.value = res.skipped ?? []
        importDegraded.value = res.degraded ?? []
        createdComposition.value = res.composition_id
            ? { id: res.composition_id, title: res.composition_title }
            : null

        if (importSkipped.value.length > 0) {
            toast.warning(`${importSkipped.value.length} 道题目被跳过，成功导入 ${res.created_count} 道`)
        } else {
            toast.success(`成功导入 ${res.created_count} 道题目`)
        }
        step.value = 'success'
    } catch (e: any) {
        // 422 且尚未决定如何处理部分失败时，交由用户选择继续或取消。
        const detail = e?.data?.detail
        if (typeof detail === 'string' && detail.includes('未能入库') && !proceedWithPartial) {
            partialFailureDetail.value = detail
            return
        }
        toast.error('导入失败', { description: detail || e.message })
    } finally {
        isImporting.value = false
    }
}

const confirmPartialImport = async () => {
    partialFailureDetail.value = null
    await handleImport(true)
}

const removeItem = (index: number) => {
    importList.value.splice(index, 1)
}

const duplicateItem = (index: number) => {
    const item = importList.value[index]
    if (!item) return
    const newItem: ImportDraft = JSON.parse(JSON.stringify(item))
    newItem.uid = `imp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    newItem.temp_id = generateTempId()
    importList.value.splice(index + 1, 0, newItem)
    // 版面上也要多出一道题，否则副本不会出现在稿件里。
    if (paper.value?.outline && item.temp_id && newItem.temp_id) {
        paper.value = {
            ...paper.value,
            outline: insertQuestionRefAfter(paper.value.outline, item.temp_id, newItem.temp_id),
        }
    }
}

const editItem = (uid: string) => {
    editingItemId.value = uid
}

const handleEditSuccess = (updatedQuestion: ImportDraft) => {
    if (editingItemId.value) {
        const index = importList.value.findIndex(i => i.uid === editingItemId.value)
        if (index !== -1) {
            importList.value[index] = updatedQuestion
        }
    }
    editingItemId.value = null
}

const getEditingItem = () => {
    return importList.value.find(item => item.uid === editingItemId.value)
}

const reset = () => {
    file.value = null
    markdownContent.value = ''
    pastedImage.value = null
    uploadedFilePath.value = null
    importList.value = []
    step.value = 'upload'
    error.value = null
    paper.value = null
    contentSha256.value = null
    duplicateOf.value = null
    saveAsComposition.value = false
    compositionTitle.value = ''
    compositionFolderId.value = null
    createdComposition.value = null
    importSkipped.value = []
    importDegraded.value = []
    idempotencyKey.value = null
    partialFailureDetail.value = null
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
                            <Textarea
                                v-model="markdownContent"
                                placeholder="将含有题目的文档内容或纯文本直接粘贴到此处..."
                                class="min-h-[250px] flex-1 resize-y font-mono text-sm"
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

                    <!-- 同时保存为稿件：默认关闭，由用户主动勾选 -->
                    <div class="mt-4 rounded-lg border p-4 space-y-4">
                        <div class="flex items-start gap-3">
                            <Checkbox
                                id="save-as-composition"
                                :model-value="saveAsComposition"
                                class="mt-1"
                                @update:model-value="(v) => saveAsComposition = v as boolean"
                            />
                            <Label for="save-as-composition" class="space-y-1 cursor-pointer font-normal">
                                <span class="text-sm font-medium block">同时保存为试卷稿件</span>
                                <span class="text-xs text-muted-foreground block">
                                    除了把题目写入题库，再生成一份可继续编辑的整卷稿件，便于下次替换少量题目后复用。
                                </span>
                            </Label>
                        </div>

                        <div v-if="saveAsComposition" class="grid grid-cols-1 md:grid-cols-2 gap-4 pl-7">
                            <div class="space-y-2">
                                <Label>稿件名称</Label>
                                <Input v-model="compositionTitle" placeholder="例如：高一第一次周测" />
                            </div>
                            <div class="space-y-2">
                                <Label>保存空间</Label>
                                <Select v-model="compositionScope">
                                    <SelectTrigger><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="personal">个人空间（仅自己可见）</SelectItem>
                                        <SelectItem value="shared">共享空间（学科内可见）</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                            <div class="space-y-2">
                                <Label>目标目录</Label>
                                <Select
                                    :model-value="compositionFolderId === null ? 'root' : String(compositionFolderId)"
                                    @update:model-value="(v) => compositionFolderId = v === 'root' ? null : Number(v)"
                                >
                                    <SelectTrigger><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="root">根目录</SelectItem>
                                        <SelectItem
                                            v-for="f in folderOptions"
                                            :key="f.id"
                                            :value="String(f.id)"
                                        >{{ f.label }}</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                            <div class="space-y-2">
                                <Label>题号处理</Label>
                                <Select
                                    :model-value="renumber ? 'renumber' : 'keep'"
                                    @update:model-value="(v) => renumber = v === 'renumber'"
                                >
                                    <SelectTrigger><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="renumber">重新连续编号</SelectItem>
                                        <SelectItem value="keep">保留原题号（可能缺号）</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                            <p v-if="!hasStructure" class="md:col-span-2 text-xs text-muted-foreground">
                                本次未识别到大题标题等版面结构，稿件将按题目顺序生成，你可以在稿件里继续补充。
                            </p>
                        </div>
                    </div>
                </CardContent>
            </Card>

            <!-- 文件级重复提示：只提示，不阻塞 -->
            <Alert v-if="duplicateOf">
                <AlertCircle class="h-4 w-4" />
                <AlertDescription>
                    检测到与此前导入内容完全相同的文件（{{ duplicateOf.original_filename }}）。你仍然可以继续导入。
                    <NuxtLink
                        v-if="duplicateOf.composition_id"
                        :to="`/compositions/shared/${duplicateOf.composition_id}`"
                        class="underline font-medium ml-1"
                    >查看上次生成的稿件</NuxtLink>
                </AlertDescription>
            </Alert>

            <!-- Question List -->
            <div class="space-y-4">
                <div v-if="importList.length === 0" class="text-center py-8 text-muted-foreground">
                    无导入的题目，请先上传文档或粘贴内容
                </div>

                <QuestionListItem 
                    v-for="(item, index) in importList"
                    :key="item.uid"
                    :item="item"
                    :index="index"
                    :all-knowledge-points="knowledgePoints"
                    @edit="editItem(item.uid)"
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

            <!-- 稿件是独立结果，单独陈述，不并入任务状态 -->
            <div v-if="createdComposition" class="rounded-lg border bg-muted/40 px-4 py-3 text-sm text-center">
                已生成稿件「{{ createdComposition.title }}」，可直接替换少量题目后复用。
            </div>

            <div v-if="importSkipped.length" class="w-full max-w-xl rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-sm">
                <p class="font-medium mb-2">{{ importSkipped.length }} 道题目被跳过</p>
                <ul class="list-disc pl-5 space-y-1 text-muted-foreground">
                    <li v-for="(s, i) in importSkipped" :key="i">{{ s.message }}</li>
                </ul>
            </div>

            <div v-if="importDegraded.length" class="w-full max-w-xl rounded-lg border p-4 text-sm">
                <p class="font-medium mb-2">以下内容做了结构降级，请在稿件中检查</p>
                <ul class="list-disc pl-5 space-y-1 text-muted-foreground">
                    <li v-for="(d, i) in importDegraded" :key="i">{{ d.reason }}：{{ d.excerpt }}</li>
                </ul>
            </div>

            <div class="flex flex-wrap gap-4 justify-center">
                <Button variant="outline" @click="reset">继续导入</Button>
                <Button v-if="createdComposition" as-child>
                    <NuxtLink :to="`/compositions/${compositionScope}/${createdComposition.id}`">打开稿件</NuxtLink>
                </Button>
                <Button as-child :variant="createdComposition ? 'outline' : 'default'" v-if="importedTaskId">
                    <NuxtLink :to="`/questions?import_task_id=${importedTaskId}`">查看本次导入题目</NuxtLink>
                </Button>
                <Button as-child v-else>
                    <NuxtLink to="/questions">查看题库</NuxtLink>
                </Button>
            </div>
        </div>

        <!-- 部分失败：由用户决定继续还是取消 -->
        <Dialog :open="!!partialFailureDetail" @update:open="(v) => !v && (partialFailureDetail = null)">
            <DialogContent>
                <DialogHeader>
                    <DialogTitle>部分题目无法入库</DialogTitle>
                    <DialogDescription>{{ partialFailureDetail }}</DialogDescription>
                </DialogHeader>
                <p class="text-sm text-muted-foreground">
                    你可以仅用已通过校验的题目继续导入（稿件也只包含这些题目），或先返回修正后再导入。
                </p>
                <DialogFooter>
                    <Button variant="outline" @click="partialFailureDetail = null">返回修正</Button>
                    <Button :disabled="isImporting" @click="confirmPartialImport">
                        <Loader2 v-if="isImporting" class="mr-2 h-4 w-4 animate-spin" />
                        仅导入已通过的题目
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    </div>
</template>
