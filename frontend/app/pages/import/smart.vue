<script setup lang="ts">
import { getApiErrorCodeMessage, getApiErrorDetail } from '@/lib/apiErrors'
import { ref, computed, watch, onMounted } from 'vue'
import { Upload, Loader2, FileText, CheckCircle2, AlertCircle, Sparkles, Trash2, Plus, Save, FileCode, Image as ImageIcon, BookOpen, Check, ChevronDown } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription } from '@/components/ui/alert'
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
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { Stepper, StepperItem, StepperIndicator, StepperTitle, StepperSeparator } from '@/components/ui/stepper'
import QuestionListItem from '@/components/QuestionListItem.vue'
import QuestionGroupReview from '@/components/import/QuestionGroupReview.vue'
import ImportDuplicateNotice from '@/components/dedup/ImportDuplicateNotice.vue'
import type { DuplicateCandidate, IntraBatchDuplicate } from '@/lib/questionDedup'
import { useDebounceFn } from '@vueuse/core'
import QuestionEditDialog from '@/components/QuestionEditDialog.vue'
import StructuredTemplateGuideDialog from '@/components/StructuredTemplateGuideDialog.vue'
import PageHeader from '@/components/PageHeader.vue'
import { toast } from 'vue-sonner'
import { zipFolder } from '@/lib/zipFolder'
import type { CompositionFolder, CompositionScope, KnowledgePoint, Subject } from '@/types'
import { buildFolderTree } from '@/lib/compositions'
import {
    hasPaperStructure,
    insertQuestionRefAfter,
    type PaperExtraction,
} from '@/lib/paperOutline'
import {
    buildImportReviewEntries,
    buildImportStructurePayload,
    validateImportStructure,
    type ImportQuestionGroup,
    type ImportStimulus,
} from '@/lib/importReview'
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

const { t } = useI18n()

// --- State ---
const step = ref<'upload' | 'review' | 'success'>('upload')
const stepIndex = computed(() => ({ upload: 1, review: 2, success: 3 })[step.value])
const activeTab = ref<'file' | 'text'>('file')
const parseMethod = ref<'ai' | 'structured'>('ai')
const importMode = ref<'extract' | 'solve'>('extract')
const file = ref<File | null>(null)
const folderInput = ref<HTMLInputElement | null>(null)
const showFormatGuide = ref(false)
// 仅 .md 文件可在前端读取纯文本做标签提示；.docx/.zip/图片无法预读，跳过校验
const fileTextPreview = ref<string | null>(null)
const markdownContent = ref('')
const pastedImage = ref<string | null>(null)
const isUploading = ref(false)
const isImporting = ref(false)
const error = ref<string | null>(null)
const importList = ref<ImportDraft[]>([])
const stimuli = ref<ImportStimulus[]>([])
const questionGroups = ref<ImportQuestionGroup[]>([])
const editingItemId = ref<string | null>(null)
const importedTaskId = ref<number | null>(null)
// 服务端签发的源文件凭据,提交时回传以关联原文件。
const sourceRef = ref<string | null>(null)

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

// 审核页告警汇总：统计存在解析告警的题目数，供顶部提示与"仅看告警项"筛选使用。
const warningCount = computed(() => importList.value.filter((i) => i.warnings?.length).length)
const selectedCount = computed(() => importList.value.filter((item) => item.selected).length)
const onlyWarnings = ref(false)
const structureErrors = computed(() => validateImportStructure(
    importList.value,
    stimuli.value,
    questionGroups.value,
    paper.value,
))
const reviewEntries = computed(() => buildImportReviewEntries(
    importList.value,
    stimuli.value,
    questionGroups.value,
    paper.value,
))
const visibleReviewEntries = computed(() => {
    if (!onlyWarnings.value) return reviewEntries.value
    return reviewEntries.value.filter((entry) => entry.kind === 'question'
        ? entry.question.warnings?.length
        : entry.members.some(({ question }) => question.warnings?.length))
})

// Global Settings
const globalSettings = ref({
    subject_id: undefined as number | undefined,
    status: 'pending' as 'draft' | 'pending' | 'published',
    source: '' as string,
})

// 标签精准解析不支持图片识别；切换到该方法时把来源切回文件/文本。
watch(parseMethod, (method) => {
    if (method === 'structured' && pastedImage.value) {
        activeTab.value = 'file'
    }
})

// 与后端 structured_parser 的宽松匹配规则保持一致（全角/半角括号 + 别名）。
const STRUCTURED_TAG_PATTERN = /[【\[]\s*(题目|题干|question|title)\s*[】\]]/i

// 粘贴文本或 .md 文件里若完全没有 【题目】 类标签，提前非阻塞提示，避免解析出空列表却不知道原因。
const structuredTagWarning = computed(() => {
    if (parseMethod.value !== 'structured') return null
    const text = activeTab.value === 'text' ? markdownContent.value : (fileTextPreview.value ?? '')
    if (!text.trim()) return null
    if (STRUCTURED_TAG_PATTERN.test(text)) return null
    return t('importSmart.alerts.tagMissing', { tag: '【题目】' })
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
    if (isUploading.value) return
    const files = e.type === 'drop'
        ? (e as DragEvent).dataTransfer?.files
        : (e.target as HTMLInputElement | null)?.files
    if (files && files.length > 0) {
        const picked = files[0]
        if (!picked) return
        file.value = picked
        // If it's an image, clear pasted image
        if (picked.type.startsWith('image/')) {
            pastedImage.value = null
        }
        error.value = null
        fileTextPreview.value = null
        if (picked.name.endsWith('.md')) {
            picked.text().then((text) => { fileTextPreview.value = text })
        }
    }
}

const handleFolderChange = async (e: Event) => {
    const target = e.target as HTMLInputElement
    if (!target.files || target.files.length === 0) return
    try {
        pastedImage.value = null
        file.value = await zipFolder(target.files, 'markdown-folder.zip')
        error.value = null
        fileTextPreview.value = null
    } catch (err: any) {
        toast.error(t('importSmart.upload.zipFailed', { error: String(err?.message ?? err) }))
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
                fileTextPreview.value = null
            }
            break
        }
    }
}

const handleAutoUpload = () => {
    if (!file.value && !pastedImage.value) return;
    if (!globalSettings.value.subject_id) {
        toast.error(t('importSmart.upload.selectSubjectFirst'))
        return
    }
    if (parseMethod.value === 'ai' && embeddingConfigured.value && !chromaReachable.value) {
        if (!confirm(t('importSmart.alerts.chromaUnreachableConfirm'))) return
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
    const drafts = toDrafts(data.questions)
    // 标签解析器缺 【题目】 标签时会静默返回空列表；留在上传页给出可操作的提示，而不是展示一个空的审核页。
    if (parseMethod.value === 'structured' && drafts.length === 0) {
        error.value = t('importSmart.alerts.noQuestionsParsed', { tag: '【题目】' })
        showFormatGuide.value = true
        return
    }
    importList.value = drafts
    duplicates.value = {}
    batchDuplicates.value = {}
    duplicatesApplied.value = false
    stimuli.value = data.stimuli ?? []
    questionGroups.value = data.question_groups ?? []
    const groupedQuestionIds = new Set(questionGroups.value.flatMap((group) => group.question_temp_ids))
    for (const draft of importList.value) {
        if (draft.temp_id && groupedQuestionIds.has(draft.temp_id)) draft.selected = true
    }
    paper.value = data.paper ?? null
    contentSha256.value = data.content_sha256 ?? null
    duplicateOf.value = data.duplicate_of ?? null
    sourceRef.value = data.source_ref ?? null
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
        for (const w of data?.warnings ?? []) toast.warning(w)
    } catch (e: any) {
        error.value = e.message
    } finally {
        isUploading.value = false
    }
}

const handleUploadMarkdown = async (isFile: boolean = false) => {
    if (isFile && !file.value) return
    if (!isFile && !markdownContent.value.trim()) {
        toast.error(t('importSmart.upload.enterMarkdown'))
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


// 逐条应用全局设置；缺答案的题降级为草稿（与后端 adapter 对齐）。
const toPayloadQuestion = (item: ImportDraft) => {
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
}

// --- 查重 ---
// 进入审核页后对全部题目预检(与题库比对 + 批内互查)。命中「重复」的独立题在每次解析后
// 默认取消勾选一次;之后以用户勾选为准 —— 勾选即视为确认录入。材料题的小题不能单独取消,只做标记。
const duplicates = ref<Record<string, DuplicateCandidate[]>>({})
const batchDuplicates = ref<Record<string, IntraBatchDuplicate[]>>({})
const duplicatesApplied = ref(false)

const groupedTempIds = computed(() => new Set(questionGroups.value.flatMap((group) => group.question_temp_ids)))
const questionNumberOf = (ref: string) => {
    const index = importList.value.findIndex((item) => item.temp_id === ref)
    return index >= 0 ? index + 1 : undefined
}
const isFlagged = (item: ImportDraft) =>
    !!item.temp_id && !!(duplicates.value[item.temp_id]?.length || batchDuplicates.value[item.temp_id]?.length)
const duplicateSummary = computed(() => {
    let existing = 0
    let similar = 0
    let batch = 0
    for (const item of importList.value) {
        if (!item.temp_id) continue
        const found = duplicates.value[item.temp_id] ?? []
        if (found.some((c) => c.level === 'duplicate')) existing++
        else if (found.length) similar++
        if (batchDuplicates.value[item.temp_id]?.length) batch++
    }
    return { existing, similar, batch, flagged: existing + similar + batch }
})

const dedupSignature = computed(() => step.value === 'review' && globalSettings.value.subject_id
    ? JSON.stringify([
        globalSettings.value.subject_id,
        importList.value.map((item) => [item.temp_id, item.q_type, item.content, item.options]),
        stimuli.value,
        questionGroups.value,
    ])
    : null)

const refreshDuplicates = useDebounceFn(async (signature: string | null) => {
    if (!signature || !globalSettings.value.subject_id) {
        duplicates.value = {}
        batchDuplicates.value = {}
        return
    }
    try {
        const structurePayload = buildImportStructurePayload(
            importList.value.map(toPayloadQuestion),
            importList.value,
            stimuli.value,
            questionGroups.value,
            paper.value,
        )
        const res = await $api<{
            duplicates: Record<string, DuplicateCandidate[]>
            intra_batch_duplicates: Record<string, IntraBatchDuplicate[]>
        }>(`/subjects/${globalSettings.value.subject_id}/paper-imports/preview`, {
            method: 'POST',
            body: { scope: compositionScope.value, ...structurePayload },
        })
        if (signature !== dedupSignature.value) return
        duplicates.value = res.duplicates ?? {}
        batchDuplicates.value = res.intra_batch_duplicates ?? {}
        if (!duplicatesApplied.value) {
            duplicatesApplied.value = true
            for (const item of importList.value) {
                if (!item.temp_id || groupedTempIds.value.has(item.temp_id)) continue
                const exact = duplicates.value[item.temp_id]?.some((c) => c.level === 'duplicate')
                    || batchDuplicates.value[item.temp_id]?.some((b) => b.level === 'duplicate')
                if (exact) item.selected = false
            }
        }
    } catch {
        // 预检失败不影响导入,提交时后端仍会复核
    }
}, 600)

watch(dedupSignature, (signature) => { refreshDuplicates(signature) })

const handleImport = async (proceedWithPartial = false) => {
    if (!globalSettings.value.subject_id) {
        toast.error(t('importSmart.upload.selectSubjectFirst'))
        return
    }

    if (structureErrors.value.length > 0) {
        toast.error(t('importSmart.review.structureInvalidToast'))
        return
    }

    const selectedItems = importList.value.filter(item => item.selected)
    if (selectedItems.length === 0) {
        toast.error(t('importSmart.review.selectAtLeastOne'))
        return
    }
    if (saveAsComposition.value && !compositionTitle.value.trim()) {
        toast.error(t('importSmart.review.compositionTitleRequired'))
        return
    }

    isImporting.value = true
    try {
        const payloadQuestions = selectedItems.map(toPayloadQuestion)

        // 幂等键绑定本次提交：网络重试不会重复建题建稿。
        idempotencyKey.value ||= generateTempId()

        const structurePayload = buildImportStructurePayload(
            payloadQuestions,
            selectedItems,
            stimuli.value,
            questionGroups.value,
            paper.value,
        )
        const preview = await $api<{
            importable_count: number
            skipped: { temp_id: string | null; message: string }[]
            blocking_reason: string | null
            blocking_code?: string | null
            blocking_params?: Record<string, unknown> | null
        }>(`/subjects/${globalSettings.value.subject_id}/paper-imports/preview`, {
            method: 'POST',
            body: { scope: compositionScope.value, ...structurePayload },
        })
        if (preview.blocking_reason) {
            toast.error(t('importSmart.review.previewFailed'), {
                description: getApiErrorCodeMessage({ data: { code: preview.blocking_code, params: preview.blocking_params } }) || preview.blocking_reason,
            })
            return
        }
        if (preview.skipped.length > 0 && !proceedWithPartial) {
            partialFailureDetail.value = t('importSmart.review.partialSkipped', {
                count: preview.skipped.length,
                messages: preview.skipped.map((item) => item.message).join(t('importSmart.review.messageSeparator')),
            })
            return
        }

        const body = {
            scope: compositionScope.value,
            ...structurePayload,
            save_as_composition: saveAsComposition.value,
            title: compositionTitle.value.trim() || null,
            folder_id: compositionFolderId.value,
            renumber: renumber.value,
            proceed_with_partial: proceedWithPartial,
            status: globalSettings.value.status,
            filename: file.value?.name ?? null,
            source_ref: sourceRef.value,
            content_sha256: contentSha256.value,
            idempotency_key: idempotencyKey.value,
            // 用户仍勾选的疑似重复题视为已确认
            allow_duplicate_temp_ids: selectedItems.filter(isFlagged).map((item) => item.temp_id),
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
            toast.warning(t('importSmart.review.importedWithSkipped', { skipped: importSkipped.value.length, created: res.created_count }))
        } else {
            toast.success(t('importSmart.review.imported', { count: res.created_count }))
        }
        step.value = 'success'
    } catch (e: any) {
        // 422 且尚未决定如何处理部分失败时，交由用户选择继续或取消。
        if (e?.data?.code === 'paper_import.partial_skipped' && !proceedWithPartial) {
            partialFailureDetail.value = getApiErrorDetail(e, e.message)
            return
        }
        toast.error(t('importSmart.review.importFailed'), { description: getApiErrorDetail(e, e.message) })
    } finally {
        isImporting.value = false
    }
}

const confirmPartialImport = async () => {
    partialFailureDetail.value = null
    await handleImport(true)
}

const removeItem = (index: number) => {
    const item = importList.value[index]
    if (paper.value?.outline && item?.temp_id) {
        paper.value = {
            ...paper.value,
            outline: paper.value.outline.filter(
                (outlineItem) => outlineItem.kind !== 'question_ref' || outlineItem.temp_id !== item.temp_id,
            ),
        }
    }
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
    fileTextPreview.value = null
    sourceRef.value = null
    importList.value = []
    stimuli.value = []
    questionGroups.value = []
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
    <PageHeader :title="t('nav.smartImport')" />
    <div class="flex flex-1 flex-col p-4 space-y-6">
        <!-- 三步流程指示：只用于展示进度，不支持点击跳转 -->
        <Stepper :model-value="stepIndex" class="max-w-4xl mx-auto w-full">
            <StepperItem
                v-for="(label, i) in [t('importSmart.steps.upload'), t('importSmart.steps.review'), t('importSmart.steps.done')]"
                :key="i"
                v-slot="{ state }"
                :step="i + 1"
                class="group relative flex-1 flex flex-col items-center gap-1.5"
            >
                <StepperSeparator
                    v-if="i < 2"
                    class="absolute left-[calc(50%+16px)] right-[calc(-50%+16px)] top-4 block h-0.5"
                />
                <StepperIndicator>
                    <Check v-if="state === 'completed'" class="h-4 w-4" />
                    <template v-else>{{ i + 1 }}</template>
                </StepperIndicator>
                <StepperTitle class="text-xs font-normal text-muted-foreground group-data-[state=active]:text-foreground group-data-[state=active]:font-medium">{{ label }}</StepperTitle>
            </StepperItem>
        </Stepper>

        <!-- Step 1: Upload -->
        <div v-if="step === 'upload'" class="w-full">
            <div class="space-y-6">
                <Alert v-if="!embeddingConfigured" class="max-w-4xl mx-auto">
                    <AlertCircle class="h-4 w-4" />
                    <AlertDescription>
                        <i18n-t scope="global" keypath="importSmart.alerts.embeddingNotConfigured">
                            <template #link><NuxtLink to="/settings" class="underline font-medium">{{ t('nav.systemSettings') }}</NuxtLink></template>
                        </i18n-t>
                    </AlertDescription>
                </Alert>
                <Alert v-else-if="!kpVectorized" class="max-w-4xl mx-auto">
                    <AlertCircle class="h-4 w-4" />
                    <AlertDescription>
                        <template v-if="isSuperuser">
                            <i18n-t scope="global" keypath="importSmart.alerts.kpNotVectorizedAdmin">
                                <template #link><NuxtLink to="/knowledge-points" class="underline font-medium">{{ t('nav.knowledgePoints') }}</NuxtLink></template>
                            </i18n-t>
                        </template>
                        <template v-else>
                            {{ t('importSmart.alerts.kpNotVectorized') }}
                        </template>
                    </AlertDescription>
                </Alert>
                <!-- Input Source Tabs -->
                <Tabs v-model="activeTab" class="w-full max-w-4xl mx-auto">
                    <TabsList class="grid w-full grid-cols-2">
                        <TabsTrigger value="file" class="gap-2">
                            <Upload class="h-4 w-4" />
                            {{ t('importSmart.tabs.file') }}
                        </TabsTrigger>
                        <TabsTrigger value="text" class="gap-2">
                            <FileCode class="h-4 w-4" />
                            {{ t('importSmart.tabs.text') }}
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
                                :title="t('importSmart.upload.inputTitle')"
                            />
                            
                            <!-- Initial State -->
                            <div v-if="!file && !pastedImage" class="space-y-6 pointer-events-none relative z-0">
                                <div class="bg-background w-20 h-20 rounded-full flex items-center justify-center mx-auto shadow-sm border">
                                    <Upload class="h-10 w-10 text-muted-foreground group-hover:text-primary transition-colors" />
                                </div>
                                <div class="space-y-2">
                                    <h3 class="text-xl font-medium">{{ t('importSmart.upload.dropTitle') }}</h3>
                                    <p class="text-sm text-muted-foreground">{{ t('importSmart.upload.pasteHint') }}</p>
                                </div>
                                <div class="flex items-center justify-center gap-4 text-xs text-muted-foreground mt-4">
                                    <span class="flex items-center gap-1"><FileText class="h-3 w-3"/> Word (.docx)</span>
                                    <span class="flex items-center gap-1"><FileCode class="h-3 w-3"/> Markdown (.md / .zip)</span>
                                    <span class="flex items-center gap-1"><ImageIcon class="h-3 w-3"/> {{ t('importSmart.upload.imageExtract') }}</span>
                                </div>
                            </div>
                            
                            <!-- File Selected State -->
                            <div v-else class="space-y-6 relative z-20 w-full max-w-md">
                                <div class="p-6 bg-background rounded-lg shadow-sm border flex flex-col items-center gap-4">
                                    <template v-if="pastedImage">
                                        <img :src="pastedImage" alt="Pasted image" class="max-h-48 rounded border shadow-sm object-contain" />
                                        <div class="text-sm font-medium text-center truncate w-full">{{ t('importSmart.upload.pastedImage') }}</div>
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
                                            {{ t('importSmart.upload.removeAndReselect') }}
                                        </Button>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <!-- Markdown 含本地图片:上传 .zip 或整个文件夹 -->
                        <div class="mt-3 text-center text-xs text-muted-foreground">
                            <i18n-t scope="global" keypath="importSmart.upload.folderHint">
                                <template #zip><span class="font-medium">.zip</span></template>
                                <template #folder><button type="button" class="underline hover:text-primary" :disabled="isUploading" @click="folderInput?.click()">{{ t('importSmart.upload.selectFolder') }}</button></template>
                            </i18n-t>
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
                                :placeholder="t('importSmart.upload.textPlaceholder')"
                                class="min-h-[250px] flex-1 resize-y font-mono text-sm"
                            />
                        </div>
                    </TabsContent>
                </Tabs>

                <!-- Parsing Settings & Submit -->
                <div class="space-y-6 bg-accent/20 rounded-xl p-6 border max-w-4xl mx-auto w-full">
                    <div>
                        <h3 class="text-lg font-medium mb-4">{{ t('importSmart.settings.title') }}</h3>
                        
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
                                        {{ t('importSmart.settings.aiMethodTitle') }}
                                    </div>
                                    <div class="text-sm text-muted-foreground mt-1">{{ t('importSmart.settings.aiMethodDescription') }}</div>
                                </div>
                            </div>
                            
                            <div
                                class="flex items-start space-x-3 border-2 rounded-lg p-4 cursor-pointer transition-all hover:bg-accent/50 bg-background"
                                :class="parseMethod === 'structured' ? 'border-primary ring-1 ring-primary shadow-sm' : 'border-muted'"
                                @click="parseMethod = 'structured'"
                            >
                                <div class="mt-0.5"><CheckCircle2 v-if="parseMethod === 'structured'" class="h-5 w-5 text-primary" /><div v-else class="h-5 w-5 rounded-full border opacity-50"/></div>
                                <div class="flex-1">
                                    <div class="text-base font-medium">{{ t('importSmart.settings.structuredMethodTitle') }}</div>
                                    <div class="text-sm text-muted-foreground mt-1">{{ t('importSmart.settings.structuredMethodDescription', { tags: '【题目】【答案】' }) }}</div>
                                    <Button
                                        variant="link"
                                        size="sm"
                                        class="h-auto p-0 mt-1 text-xs"
                                        @click.stop="showFormatGuide = true"
                                    >
                                        <BookOpen class="h-3 w-3 mr-1" />{{ t('importSmart.settings.viewTagGuide') }}
                                    </Button>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Dynamic Sub-settings based on parse method -->
                    <div class="pl-4 border-l-2 border-primary/20 space-y-4 pt-2">
                        <!-- AI Sub-settings -->
                        <template v-if="parseMethod === 'ai'">
                            <Label class="text-sm font-medium text-foreground">{{ t('importSmart.settings.aiModeLabel') }}</Label>
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
                                        <div class="text-sm font-medium">{{ t('importSmart.settings.extractTitle') }}</div>
                                        <div class="text-xs text-muted-foreground">{{ t('importSmart.settings.extractDescription') }}</div>
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
                                        <div class="text-sm font-medium">{{ t('importSmart.settings.solveTitle') }}</div>
                                        <div class="text-xs text-muted-foreground">{{ t('importSmart.settings.solveDescription') }}</div>
                                    </div>
                                </div>
                            </div>
                        </template>
                        
                        <!-- Structured Sub-settings -->
                        <template v-if="parseMethod === 'structured'">
                            <div class="rounded-md bg-background border p-4 text-sm text-muted-foreground flex items-start gap-2">
                                <AlertCircle class="h-4 w-4 text-amber-500 shrink-0 mt-0.5" />
                                <div class="flex-1 space-y-2">
                                    <p class="font-medium text-foreground">{{ t('importSmart.settings.templateTitle') }}</p>
                                    <i18n-t scope="global" keypath="importSmart.settings.templateBody" tag="p">
                                        <template #tag><Badge variant="outline">【题目】</Badge></template>
                                    </i18n-t>
                                    <div class="flex flex-wrap gap-1.5">
                                        <Badge variant="secondary">【选项】</Badge>
                                        <Badge variant="secondary">【答案】</Badge>
                                        <Badge variant="secondary">【解析】</Badge>
                                        <Badge variant="secondary">【答案区】</Badge>
                                    </div>
                                    <Button variant="outline" size="sm" @click="showFormatGuide = true">
                                        <BookOpen class="h-3.5 w-3.5 mr-1.5" />{{ t('importSmart.settings.viewFullGuide') }}
                                    </Button>
                                </div>
                            </div>
                        </template>
                    </div>

                    <!-- Final Action -->
                    <div class="pt-4 mt-4 border-t">
                        <Alert v-if="structuredTagWarning" class="mb-3">
                            <AlertCircle class="h-4 w-4" />
                            <AlertDescription>
                                {{ structuredTagWarning }}
                                <button type="button" class="underline font-medium ml-1" @click="showFormatGuide = true">{{ t('importSmart.settings.viewGuide') }}</button>
                            </AlertDescription>
                        </Alert>
                        <Button 
                            class="w-full text-lg h-14 shadow-lg transition-all" 
                            :class="parseMethod === 'ai' ? 'bg-primary' : 'bg-slate-800 hover:bg-slate-900 dark:bg-slate-700'" 
                            @click="handleAutoUpload" 
                            :disabled="(!file && !pastedImage && !markdownContent.trim()) || isUploading"
                        >
                            <Loader2 v-if="isUploading" class="mr-2 h-6 w-6 animate-spin" />
                            <Sparkles v-else-if="parseMethod === 'ai'" class="mr-2 h-6 w-6" />
                            <FileCode v-else class="mr-2 h-6 w-6" />
                            {{ isUploading ? t('importSmart.submit.uploading') : (parseMethod === 'ai' ? t('importSmart.submit.ai') : t('importSmart.submit.structured')) }}
                        </Button>
                        <p v-if="(!file && !pastedImage && !markdownContent.trim())" class="text-center text-sm text-destructive mt-3">
                            {{ t('importSmart.submit.empty') }}
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

        <!-- Step 2: Review -->
        <div v-if="step === 'review'" class="space-y-6">
            <!-- 文件级重复提示：只提示，不阻塞 -->
            <Alert v-if="duplicateOf">
                <AlertCircle class="h-4 w-4" />
                <AlertDescription>
                    {{ t('importSmart.review.duplicate', { filename: duplicateOf.original_filename ?? '' }) }}
                    <NuxtLink
                        v-if="duplicateOf.composition_id"
                        :to="`/compositions/shared/${duplicateOf.composition_id}`"
                        class="underline font-medium ml-1"
                    >{{ t('importSmart.review.viewLastComposition') }}</NuxtLink>
                </AlertDescription>
            </Alert>

            <!-- Question List -->
            <div class="space-y-4 pb-4">
                <Alert v-if="structureErrors.length" variant="destructive">
                    <AlertCircle class="h-4 w-4" />
                    <AlertDescription>
                        <p class="font-medium">{{ t('importSmart.review.structureInvalid') }}</p>
                        <ul class="mt-2 list-disc space-y-1 pl-5">
                            <li v-for="message in structureErrors" :key="message">{{ message }}</li>
                        </ul>
                    </AlertDescription>
                </Alert>
                <div v-if="importList.length === 0" class="text-center py-8 text-muted-foreground">
                    {{ t('importSmart.review.empty') }}
                </div>
                <Alert v-if="duplicateSummary.flagged" class="border-amber-500/50 bg-amber-500/5">
                    <AlertCircle class="h-4 w-4 text-amber-600" />
                    <AlertDescription>
                        {{ t('questionDedup.import.summary', { total: importList.length, existing: duplicateSummary.existing, similar: duplicateSummary.similar, batch: duplicateSummary.batch }) }}
                    </AlertDescription>
                </Alert>

                <template v-for="entry in visibleReviewEntries" :key="entry.kind === 'question' ? entry.question.uid : entry.group.temp_id">
                    <ImportDuplicateNotice
                        v-if="entry.kind === 'question' && entry.question.temp_id"
                        :candidates="duplicates[entry.question.temp_id]"
                        :batch="batchDuplicates[entry.question.temp_id]"
                        :number-of="questionNumberOf"
                    />
                    <QuestionListItem
                        v-if="entry.kind === 'question'"
                        :item="entry.question"
                        :index="entry.index"
                        :all-knowledge-points="knowledgePoints"
                        :selected="entry.question.selected"
                        selectable
                        @select="entry.question.selected = $event"
                        @edit="editItem(entry.question.uid)"
                        @delete="removeItem(entry.index)"
                        @duplicate="duplicateItem(entry.index)"
                    />
                    <QuestionGroupReview
                        v-else
                        :entry="entry"
                        :duplicates="duplicates"
                        :batch-duplicates="batchDuplicates"
                        :number-of="questionNumberOf"
                        :all-knowledge-points="knowledgePoints"
                        @edit="editItem"
                    />
                </template>

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

            <div class="sticky bottom-3 z-20 -mx-1 overflow-hidden rounded-lg border bg-background/95 shadow-[0_-8px_28px_rgba(0,0,0,0.10)] backdrop-blur supports-[backdrop-filter]:bg-background/90">
                <div v-if="saveAsComposition" class="border-b bg-muted/20 px-4 py-3">
                    <div class="mb-3 flex items-center justify-between">
                        <div class="flex items-center gap-2">
                            <FileText class="h-4 w-4 text-primary" />
                            <span class="text-sm font-medium">{{ t('importSmart.composition.settings') }}</span>
                            <span class="hidden text-xs text-muted-foreground sm:inline">{{ t('importSmart.composition.hint') }}</span>
                        </div>
                        <Button variant="ghost" size="icon" class="h-7 w-7" :title="t('importSmart.composition.collapse')" @click="saveAsComposition = false">
                            <ChevronDown class="h-4 w-4" />
                            <span class="sr-only">{{ t('importSmart.composition.collapse') }}</span>
                        </Button>
                    </div>
                    <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-12">
                        <div class="space-y-1.5 xl:col-span-4">
                            <Label class="text-xs text-muted-foreground">{{ t('importSmart.composition.title') }}</Label>
                            <Input v-model="compositionTitle" :placeholder="t('importSmart.composition.titlePlaceholder')" class="h-9 bg-background" />
                        </div>
                        <div class="space-y-1.5 xl:col-span-3">
                            <Label class="text-xs text-muted-foreground">{{ t('importSmart.composition.scope') }}</Label>
                            <Select v-model="compositionScope">
                                <SelectTrigger class="h-9 bg-background"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="personal">{{ t('importSmart.composition.scopePersonal') }}</SelectItem>
                                    <SelectItem value="shared">{{ t('importSmart.composition.scopeShared') }}</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        <div class="space-y-1.5 xl:col-span-2">
                            <Label class="text-xs text-muted-foreground">{{ t('importSmart.composition.folder') }}</Label>
                            <Select
                                :model-value="compositionFolderId === null ? 'root' : String(compositionFolderId)"
                                @update:model-value="(v) => compositionFolderId = v === 'root' ? null : Number(v)"
                            >
                                <SelectTrigger class="h-9 bg-background"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="root">{{ t('importSmart.composition.rootFolder') }}</SelectItem>
                                    <SelectItem v-for="f in folderOptions" :key="f.id" :value="String(f.id)">{{ f.label }}</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        <div class="space-y-1.5 xl:col-span-3">
                            <Label class="text-xs text-muted-foreground">{{ t('importSmart.composition.numbering') }}</Label>
                            <Select :model-value="renumber ? 'renumber' : 'keep'" @update:model-value="(v) => renumber = v === 'renumber'">
                                <SelectTrigger class="h-9 bg-background"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="renumber">{{ t('importSmart.composition.renumber') }}</SelectItem>
                                    <SelectItem value="keep">{{ t('importSmart.composition.keepNumber') }}</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                    </div>
                    <p v-if="!hasStructure" class="mt-2 text-xs text-muted-foreground">
                        {{ t('importSmart.composition.noStructure') }}
                    </p>
                </div>

                <div class="flex min-h-16 flex-col gap-3 px-4 py-3 lg:flex-row lg:items-center">
                    <div class="flex flex-wrap items-center gap-2 rounded-md bg-muted/40 px-2.5 py-2">
                        <label class="flex shrink-0 cursor-pointer select-none items-center gap-2 text-sm font-medium">
                            <Checkbox :model-value="saveAsComposition" @update:model-value="(v) => saveAsComposition = v as boolean" />
                            {{ t('importSmart.composition.saveAs') }}
                        </label>
                        <Separator orientation="vertical" class="hidden h-5 sm:block" />
                        <div class="flex items-center gap-1.5">
                            <Label class="shrink-0 text-xs text-muted-foreground">{{ t('importSmart.review.status') }}</Label>
                            <Select v-model="globalSettings.status">
                                <SelectTrigger class="h-8 w-[124px] bg-background text-xs"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="draft">{{ t('questions.statuses.draft') }}</SelectItem>
                                    <SelectItem value="pending">{{ t('questions.statuses.pending') }}</SelectItem>
                                    <SelectItem value="published">{{ t('questions.statuses.published') }}</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        <div class="flex min-w-[180px] flex-1 items-center gap-1.5 sm:max-w-[280px]">
                            <Label class="shrink-0 text-xs text-muted-foreground">{{ t('importSmart.review.source') }}</Label>
                            <Input v-model="globalSettings.source" :placeholder="t('importSmart.review.sourcePlaceholder')" class="h-8 bg-background text-xs" />
                        </div>
                    </div>
                    <div class="flex flex-1 items-center justify-between gap-3 lg:justify-end">
                        <div class="flex items-center gap-2">
                            <button
                                v-if="warningCount > 0"
                                type="button"
                                :aria-pressed="onlyWarnings"
                                :title="t('importSmart.review.onlyWarnings')"
                                @click="onlyWarnings = !onlyWarnings"
                            >
                                <Badge variant="outline" :class="onlyWarnings ? 'border-amber-500 bg-amber-500/10 text-amber-700 dark:text-amber-400' : 'text-amber-600 dark:text-amber-400'">
                                    <AlertCircle class="mr-1 h-3.5 w-3.5" />{{ t('importSmart.review.warningCount', { count: warningCount }) }}
                                </Badge>
                            </button>
                            <i18n-t scope="global" keypath="importSmart.review.selected" tag="span" class="whitespace-nowrap text-sm text-muted-foreground">
                                <template #selected><strong class="font-medium text-foreground">{{ selectedCount }}</strong></template>
                                <template #total>{{ importList.length }}</template>
                            </i18n-t>
                        </div>
                        <div class="flex items-center gap-2">
                            <Button variant="ghost" :disabled="isImporting" @click="reset">{{ t('common.cancel') }}</Button>
                            <Button class="min-w-[148px]" @click="handleImport()" :disabled="isImporting || selectedCount === 0 || structureErrors.length > 0">
                                <Loader2 v-if="isImporting" class="mr-2 h-4 w-4 animate-spin" />
                                <Save v-else class="mr-2 h-4 w-4" />
                                {{ t('importSmart.review.confirmImport', { count: selectedCount }) }}
                            </Button>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Step 3: Success -->
        <div v-if="step === 'success'" class="flex flex-col items-center justify-center py-12 space-y-4">
            <div class="rounded-full bg-green-100 p-3 dark:bg-green-900/20">
                <CheckCircle2 class="h-12 w-12 text-green-600 dark:text-green-400" />
            </div>
            <h2 class="text-2xl font-bold">{{ t('importSmart.success.title') }}</h2>
            <p class="text-muted-foreground">{{ t('importSmart.success.description') }}</p>

            <!-- 稿件是独立结果，单独陈述，不并入任务状态 -->
            <div v-if="createdComposition" class="rounded-lg border bg-muted/40 px-4 py-3 text-sm text-center">
                {{ t('importSmart.success.composition', { title: createdComposition.title }) }}
            </div>

            <div v-if="importSkipped.length" class="w-full max-w-xl rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-sm">
                <p class="font-medium mb-2">{{ t('importSmart.success.skipped', { count: importSkipped.length }) }}</p>
                <ul class="list-disc pl-5 space-y-1 text-muted-foreground">
                    <li v-for="(s, i) in importSkipped" :key="i">{{ s.message }}</li>
                </ul>
            </div>

            <div v-if="importDegraded.length" class="w-full max-w-xl rounded-lg border p-4 text-sm">
                <p class="font-medium mb-2">{{ t('importSmart.success.degraded') }}</p>
                <ul class="list-disc pl-5 space-y-1 text-muted-foreground">
                    <li v-for="(d, i) in importDegraded" :key="i">{{ t('importSmart.success.degradedItem', { reason: d.reason, excerpt: d.excerpt }) }}</li>
                </ul>
            </div>

            <div class="flex flex-wrap gap-4 justify-center">
                <Button variant="outline" @click="reset">{{ t('importSmart.success.continue') }}</Button>
                <Button v-if="createdComposition" as-child>
                    <NuxtLink :to="`/compositions/${compositionScope}/${createdComposition.id}`">{{ t('importSmart.success.openComposition') }}</NuxtLink>
                </Button>
                <Button as-child :variant="createdComposition ? 'outline' : 'default'" v-if="importedTaskId">
                    <NuxtLink :to="`/questions?import_task_id=${importedTaskId}`">{{ t('importSmart.success.viewImported') }}</NuxtLink>
                </Button>
                <Button as-child v-else>
                    <NuxtLink to="/questions">{{ t('importSmart.success.viewBank') }}</NuxtLink>
                </Button>
            </div>
        </div>

        <!-- 部分失败：由用户决定继续还是取消 -->
        <Dialog :open="!!partialFailureDetail" @update:open="(v) => !v && (partialFailureDetail = null)">
            <DialogContent>
                <DialogHeader>
                    <DialogTitle>{{ t('importSmart.partial.title') }}</DialogTitle>
                    <DialogDescription>{{ partialFailureDetail }}</DialogDescription>
                </DialogHeader>
                <p class="text-sm text-muted-foreground">
                    {{ t('importSmart.partial.description') }}
                </p>
                <DialogFooter>
                    <Button variant="outline" @click="partialFailureDetail = null">{{ t('importSmart.partial.back') }}</Button>
                    <Button :disabled="isImporting" @click="confirmPartialImport">
                        <Loader2 v-if="isImporting" class="mr-2 h-4 w-4 animate-spin" />
                        {{ t('importSmart.partial.confirm') }}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>

        <StructuredTemplateGuideDialog :open="showFormatGuide" @update:open="(v) => showFormatGuide = v" />
    </div>
</template>
