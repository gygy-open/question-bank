<script setup lang="ts">
import { ref, onActivated, onDeactivated, onUnmounted, computed, watch } from 'vue'
import { Upload, FileText, CheckCircle, XCircle, Loader2, Ban, Trash2, RefreshCw, ExternalLink, AlertCircle, RotateCcw, Sparkles } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  Pagination,
  PaginationEllipsis,
  PaginationFirst,
  PaginationLast,
  PaginationContent,
  PaginationItem,
  PaginationNext,
  PaginationPrevious,
} from '@/components/ui/pagination'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import PageHeader from '@/components/PageHeader.vue'
import ImportTaskDuplicatesDialog from '@/components/dedup/ImportTaskDuplicatesDialog.vue'
import type { DuplicateCandidate } from '@/lib/questionDedup'
import { toast } from 'vue-sonner'
import { zipFolder } from '@/lib/zipFolder'
import { formatDateTime } from '@/lib/locale'

definePageMeta({
    layout: 'default',
})

interface ImportTask {
    id: number
    original_filename: string
    status: string
    created_at: string
    error_message?: string
    result_summary?: string
    description?: string
    source?: string
    owner_name?: string
}

interface QueueStats {
    pending: number
    processing: number
    completed: number
    failed: number
    cancelled: number
}

interface User {
    id: number
    full_name: string
    username: string
}

const tasks = ref<ImportTask[]>([])
useAiScene().useSceneWhileMounted('import_review')
const queueStats = ref<QueueStats>({ pending: 0, processing: 0, completed: 0, failed: 0, cancelled: 0 })
const isUploading = ref(false)
const isDragging = ref(false)
const folderInput = ref<HTMLInputElement | null>(null)
const pollingInterval = ref<NodeJS.Timeout | null>(null)
const page = ref(1)
const pageSize = ref(10)
const total = ref(0)
const statusFilter = ref<string>('all')
const userFilter = ref<string>('all')
const users = ref<User[]>([])
const selectedTasks = ref<number[]>([])
const importMode = ref<'extract' | 'solve'>('extract')

const { $api } = useNuxtApp()
const { user: currentUser } = useAuth()
const { t } = useI18n()

const allSelected = computed(() => {
    return tasks.value.length > 0 && tasks.value.every(task => selectedTasks.value.includes(task.id))
})

const toggleSelectAll = (checked: boolean) => {
    if (checked) {
        selectedTasks.value = tasks.value.map(task => task.id)
    } else {
        selectedTasks.value = []
    }
}

const toggleSelectTask = (taskId: number, checked: boolean) => {
    if (checked) {
        selectedTasks.value.push(taskId)
    } else {
        selectedTasks.value = selectedTasks.value.filter(id => id !== taskId)
    }
}

const batchRetryTasks = async () => {
    if (selectedTasks.value.length === 0) return
    if (!confirm(t('importTasks.batchRetryConfirm', { count: selectedTasks.value.length }))) return

    let successCount = 0
    for (const taskId of selectedTasks.value) {
        try {
            await $api(`/imports/${taskId}/retry`, { method: 'POST' })
            successCount++
        } catch (e) {
            console.error(`Failed to retry task ${taskId}`, e)
        }
    }
    
    toast.success(t('importTasks.batchRetried', { count: successCount }))
    selectedTasks.value = []
    await fetchTasks()
}

const fetchUsers = async () => {
    if (!currentUser.value?.is_superuser) return
    try {
        const data: any = await $api('/users', {
            query: { limit: 100 }
        })
        if (data) {
            users.value = data
        }
    } catch (e) {
        console.error('Failed to fetch users', e)
    }
}

watch(() => currentUser.value, (newUser) => {
    if (newUser?.is_superuser) {
        fetchUsers()
    }
}, { immediate: true })

const fetchQueueStatus = async () => {
    try {
        const data: any = await $api('/imports/queue-status')
        if (data) {
            queueStats.value = data.stats
        }
    } catch (e) {
        console.error('Failed to fetch queue status', e)
    }
}

const fetchTasks = async () => {
    try {
        const query: any = {
            page: page.value,
            size: pageSize.value
        }
        if (statusFilter.value && statusFilter.value !== 'all') {
            query.status = statusFilter.value
        }
        if (userFilter.value && userFilter.value !== 'all') {
            query.user_id = userFilter.value
        }

        const data: any = await $api('/imports', {
            query
        })
        if (data) {
            tasks.value = data.items
            total.value = data.total
        }
    } catch (e) {
        console.error(e)
    }
}

watch(page, () => {
    fetchTasks()
})

watch(statusFilter, () => {
    page.value = 1
    fetchTasks()
})

watch(userFilter, () => {
    page.value = 1
    fetchTasks()
})

const handleFileChange = async (event: Event) => {
    const target = event.target as HTMLInputElement
    if (target.files && target.files.length > 0) {
        await uploadFiles(Array.from(target.files))
        target.value = '' // Reset input
    }
}

const handleFolderChange = async (event: Event) => {
    const target = event.target as HTMLInputElement
    if (!target.files || target.files.length === 0) return
    try {
        isUploading.value = true
        const zipped = await zipFolder(target.files, 'markdown-folder.zip')
        await uploadFiles([zipped])
    } catch (err: any) {
        toast.error(t('importTasks.upload.zipFailed'), { description: String(err?.message ?? err) })
    } finally {
        isUploading.value = false
        target.value = ''
    }
}

const handleDragOver = (e: DragEvent) => {
    isDragging.value = true
}

const handleDragLeave = (e: DragEvent) => {
    isDragging.value = false
}

const handleDrop = async (e: DragEvent) => {
    isDragging.value = false
    const files = e.dataTransfer?.files
    if (files && files.length > 0) {
        await uploadFiles(Array.from(files))
    }
}

const uploadFiles = async (files: File[]) => {
    isUploading.value = true
    const formData = new FormData()
    files.forEach(file => {
        formData.append('files', file)
    })

    try {
        const data: any = await $api(`/imports?mode=${importMode.value}`, {
            method: 'POST',
            body: formData
        })

        toast.success(t('importTasks.upload.created', { count: data?.length || 0 }))
        page.value = 1 // Reset to first page
        await fetchTasks()
    } catch (e) {
        console.error(e)
        toast.error(t('common.uploadFailed'), {
            description: String(e)
        })
    } finally {
        isUploading.value = false
    }
}

const cancelTask = async (taskId: number) => {
    if (!confirm(t('importTasks.cancelConfirm'))) return
    
    try {
        await $api(`/imports/${taskId}/cancel`, { method: 'POST' })
        toast.success(t('importTasks.cancelled'))
        await fetchTasks()
    } catch (e) {
        toast.error(t('importTasks.cancelFailed'))
    }
}

const retryTask = async (taskId: number) => {
    try {
        await $api(`/imports/${taskId}/retry`, { method: 'POST' })
        toast.success(t('importTasks.retried'))
        await fetchTasks()
    } catch (e) {
        toast.error(t('importTasks.retryFailed'))
    }
}

const resetStuckTasks = async () => {
    if (!confirm(t('importTasks.resetStuckConfirm'))) return
    
    try {
        const data: any = await $api('/imports/reset-stuck', { method: 'POST' })
        toast.success(t('importTasks.resetDone', { count: data.count }))
        await fetchQueueStatus()
        await fetchTasks()
    } catch (e) {
        toast.error(t('importTasks.resetFailed'))
    }
}

const deleteTask = async (taskId: number) => {
    if (!confirm(t('importTasks.deleteConfirm'))) return
    
    try {
        await $api(`/imports/${taskId}`, { method: 'DELETE' })
        toast.success(t('importTasks.deleted'))
        await fetchTasks()
    } catch (e) {
        toast.error(t('importTasks.deleteFailed'))
    }
}

const startPolling = () => {
    stopPolling()
    pollingInterval.value = setInterval(async () => {
        await fetchQueueStatus()
        const hasActive = tasks.value.some(task => ['pending', 'processing'].includes(task.status))
        if (hasActive) {
            await fetchTasks()
        }
    }, 5000)
}

const stopPolling = () => {
    if (pollingInterval.value) {
        clearInterval(pollingInterval.value)
        pollingInterval.value = null
    }
}

// 页面被 keepalive 缓存：离开时停止轮询，返回时刷新。
onActivated(() => {
    fetchQueueStatus()
    fetchTasks()
    startPolling()
})

onDeactivated(stopPolling)
onUnmounted(stopPolling)

const statusVariant = (status: string) => {
    switch (status) {
        case 'pending': return 'secondary'
        case 'processing': return 'default'
        case 'completed': return 'success'
        case 'failed': return 'destructive'
        case 'cancelled': return 'outline'
        default: return 'secondary'
    }
}

const TASK_STATUSES = ['pending', 'processing', 'completed', 'failed', 'cancelled'] as const

const statusLabel = (status: string) => {
    return (TASK_STATUSES as readonly string[]).includes(status) ? t(`importTasks.statuses.${status}`) : status
}

const parseSummary = (summaryJson?: string): Record<string, any> => {
    if (!summaryJson) return {}
    try {
        return JSON.parse(summaryJson) ?? {}
    } catch (e) {
        return {}
    }
}

const getResultCount = (summaryJson?: string) => {
    const summary = parseSummary(summaryJson)
    return summary.count || summary.created_question_ids?.length || 0
}

// 后台导入不拦截疑似重复,只在结果里记录(新题 id → 候选),这里供用户核对并删除
const getDuplicates = (summaryJson?: string): Record<string, DuplicateCandidate[]> =>
    parseSummary(summaryJson).duplicates ?? {}
const duplicatesOpen = ref(false)
const duplicatesOf = ref<Record<string, DuplicateCandidate[]>>({})
const openDuplicates = (summaryJson?: string) => {
    duplicatesOf.value = getDuplicates(summaryJson)
    duplicatesOpen.value = true
}
</script>

<template>
    <PageHeader :title="t('importTasks.title')">
        <template #actions>
            <Button v-if="selectedTasks.length > 0" variant="outline" @click="batchRetryTasks">
                <RefreshCw class="mr-2 h-4 w-4" />
                {{ t('importTasks.batchRetry', { count: selectedTasks.length }) }}
            </Button>
            <Button v-if="queueStats.processing > 0" variant="outline" @click="resetStuckTasks">
                <RotateCcw class="mr-2 h-4 w-4" />
                {{ t('importTasks.resetStuck') }}
            </Button>
        </template>
    </PageHeader>

    <div class="py-6 space-y-8 px-4">
        <!-- Queue Stats -->
        <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
            <Card>
                <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle class="text-sm font-medium">{{ t('importTasks.statuses.pending') }}</CardTitle>
                    <Loader2 class="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                    <div class="text-2xl font-bold">{{ queueStats.pending }}</div>
                </CardContent>
            </Card>
            <Card>
                <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle class="text-sm font-medium">{{ t('importTasks.statuses.processing') }}</CardTitle>
                    <RefreshCw class="h-4 w-4 text-muted-foreground animate-spin" />
                </CardHeader>
                <CardContent>
                    <div class="text-2xl font-bold">{{ queueStats.processing }}</div>
                </CardContent>
            </Card>
            <Card>
                <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle class="text-sm font-medium">{{ t('importTasks.statuses.completed') }}</CardTitle>
                    <CheckCircle class="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                    <div class="text-2xl font-bold">{{ queueStats.completed }}</div>
                </CardContent>
            </Card>
            <Card>
                <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle class="text-sm font-medium">{{ t('importTasks.statuses.failed') }}</CardTitle>
                    <XCircle class="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                    <div class="text-2xl font-bold">{{ queueStats.failed }}</div>
                </CardContent>
            </Card>
             <Card>
                <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle class="text-sm font-medium">{{ t('importTasks.statuses.cancelled') }}</CardTitle>
                    <Ban class="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                    <div class="text-2xl font-bold">{{ queueStats.cancelled }}</div>
                </CardContent>
            </Card>
        </div>

        <!-- Upload Area -->
        <Card>
            <CardHeader>
                <CardTitle>{{ t('importTasks.upload.title') }}</CardTitle>
                <CardDescription>{{ t('importTasks.upload.description') }}</CardDescription>
            </CardHeader>
            <CardContent class="space-y-6">
                <!-- Mode Selection -->
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
                            <div class="font-medium">{{ t('importTasks.upload.extractTitle') }}</div>
                            <div class="text-sm text-muted-foreground mt-1">{{ t('importTasks.upload.extractDescription') }}</div>
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
                                {{ t('importTasks.upload.solveTitle') }}
                                <Sparkles class="h-3 w-3 text-amber-500" />
                            </div>
                            <div class="text-sm text-muted-foreground mt-1">{{ t('importTasks.upload.solveDescription') }}</div>
                        </div>
                    </div>
                </div>

                <div class="border-2 border-dashed rounded-lg p-10 text-center transition-colors flex flex-col items-center justify-center min-h-[200px]"
                    :class="{ 
                        'opacity-50 pointer-events-none': isUploading,
                        'bg-muted/50 border-primary': isDragging,
                        'hover:bg-muted/50': !isDragging
                    }"
                    @dragover.prevent="handleDragOver"
                    @dragleave.prevent="handleDragLeave"
                    @drop.prevent="handleDrop">
                    <input type="file" multiple accept=".docx,.md,.zip" class="hidden" id="file-upload"
                        @change="handleFileChange" :disabled="isUploading">
                    <input ref="folderInput" type="file" webkitdirectory directory multiple class="hidden"
                        @change="handleFolderChange" :disabled="isUploading">
                    <label for="file-upload"
                        class="cursor-pointer flex flex-col items-center gap-4 w-full h-full justify-center">
                        <div class="p-4 bg-primary/10 rounded-full">
                            <Upload class="h-10 w-10 text-primary" />
                        </div>
                        <div class="space-y-1">
                            <span class="text-lg font-medium block">{{ t('importTasks.upload.pick') }}</span>
                            <span class="text-sm text-muted-foreground">{{ t('importTasks.upload.hint') }}</span>
                        </div>
                    </label>
                    <div class="mt-2 text-xs text-muted-foreground">
                        <i18n-t scope="global" keypath="importTasks.upload.folderHint">
                            <template #zip><span class="font-medium">.zip</span></template>
                            <template #folder><button type="button" class="underline hover:text-primary" :disabled="isUploading" @click="folderInput?.click()">{{ t('importTasks.upload.selectFolder') }}</button></template>
                        </i18n-t>
                    </div>
                    <div v-if="isUploading" class="mt-4 flex items-center text-sm text-muted-foreground">
                        <Loader2 class="mr-2 h-4 w-4 animate-spin" /> {{ t('importTasks.upload.uploading') }}
                    </div>
                </div>
            </CardContent>
        </Card>

        <!-- Task List -->
        <Card>
            <CardHeader class="flex flex-row items-center justify-between">
                <div>
                    <CardTitle>{{ t('importTasks.list.title') }}</CardTitle>
                    <CardDescription>{{ t('importTasks.list.description') }}</CardDescription>
                </div>
                <div class="flex gap-2">
                    <div class="w-[180px]" v-if="currentUser?.is_superuser">
                        <Select v-model="userFilter">
                            <SelectTrigger>
                                <SelectValue :placeholder="t('importTasks.list.filterUser')" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">{{ t('importTasks.list.allUsers') }}</SelectItem>
                                <SelectItem v-for="user in users" :key="user.id" :value="String(user.id)">
                                    {{ user.full_name || user.username }}
                                </SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    <div class="w-[180px]">
                        <Select v-model="statusFilter">
                            <SelectTrigger>
                                <SelectValue :placeholder="t('importTasks.list.filterStatus')" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">{{ t('importTasks.list.allStatuses') }}</SelectItem>
                                <SelectItem value="pending">{{ t('importTasks.statuses.pending') }}</SelectItem>
                                <SelectItem value="processing">{{ t('importTasks.statuses.processing') }}</SelectItem>
                                <SelectItem value="completed">{{ t('importTasks.statuses.completed') }}</SelectItem>
                                <SelectItem value="failed">{{ t('importTasks.statuses.failed') }}</SelectItem>
                                <SelectItem value="cancelled">{{ t('importTasks.statuses.cancelled') }}</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                </div>
            </CardHeader>
            <CardContent>
                <Table>
                    <TableHeader>
                        <TableRow>
                            <TableHead class="w-[50px]">
                                <Checkbox :model-value="allSelected" @update:model-value="toggleSelectAll" />
                            </TableHead>
                            <TableHead class="w-[300px]">{{ t('importTasks.list.filename') }}</TableHead>
                            <TableHead>{{ t('importTasks.list.owner') }}</TableHead>
                            <TableHead>{{ t('importTasks.list.status') }}</TableHead>
                            <TableHead>{{ t('importTasks.list.result') }}</TableHead>
                            <TableHead>{{ t('importTasks.list.createdAt') }}</TableHead>
                            <TableHead class="text-right">{{ t('common.actions') }}</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        <TableRow v-if="tasks.length === 0">
                            <TableCell colspan="7" class="text-center py-8 text-muted-foreground">
                                {{ t('importTasks.list.empty') }}
                            </TableCell>
                        </TableRow>
                        <TableRow v-for="task in tasks" :key="task.id">
                            <TableCell>
                                <Checkbox 
                                    :model-value="selectedTasks.includes(task.id)" 
                                    @update:model-value="(checked) => toggleSelectTask(task.id, checked)" 
                                />
                            </TableCell>
                            <TableCell class="font-medium">
                                <div class="flex items-center gap-2">
                                    <FileText class="h-4 w-4 text-muted-foreground" />
                                    <span class="truncate max-w-[250px]" :title="task.original_filename">
                                        {{ task.original_filename }}
                                    </span>
                                </div>
                            </TableCell>
                            <TableCell>{{ task.owner_name || '-' }}</TableCell>
                            <TableCell>
                                <Badge :variant="statusVariant(task.status) as any">
                                    <Loader2 v-if="task.status === 'processing'" class="mr-1 h-3 w-3 animate-spin" />
                                    {{ statusLabel(task.status) }}
                                </Badge>
                            </TableCell>
                            <TableCell>
                                <div v-if="task.status === 'completed'" class="space-y-1">
                                    <div class="text-sm text-green-600 flex items-center gap-1">
                                        <CheckCircle class="h-3 w-3" />
                                        {{ t('importTasks.list.extracted', { count: getResultCount(task.result_summary) }) }}
                                    </div>
                                    <button
                                        v-if="Object.keys(getDuplicates(task.result_summary)).length"
                                        type="button"
                                        class="flex items-center gap-1 text-sm text-amber-600 hover:underline"
                                        @click="openDuplicates(task.result_summary)"
                                    >
                                        <AlertCircle class="h-3 w-3" />
                                        {{ t('questionDedup.task.badge', { count: Object.keys(getDuplicates(task.result_summary)).length }) }}
                                    </button>
                                </div>
                                <div v-else-if="task.status === 'failed'" class="text-sm text-destructive flex items-center gap-1">
                                    <TooltipProvider>
                                        <Tooltip>
                                            <TooltipTrigger>
                                                <div class="flex items-center gap-1 cursor-help">
                                                    <AlertCircle class="h-3 w-3" />
                                                    <span>{{ t('importTasks.list.processFailed') }}</span>
                                                </div>
                                            </TooltipTrigger>
                                            <TooltipContent>
                                                <p class="max-w-xs break-words">{{ task.error_message || t('common.unknownError') }}</p>
                                            </TooltipContent>
                                        </Tooltip>
                                    </TooltipProvider>
                                </div>
                                <span v-else class="text-muted-foreground text-sm">-</span>
                            </TableCell>
                            <TableCell class="text-muted-foreground text-sm">
                                {{ formatDateTime(task.created_at + 'Z') }}
                            </TableCell>
                            <TableCell class="text-right">
                                <div class="flex justify-end gap-2">
                                    <!-- Actions for Pending/Processing -->
                                    <Button v-if="['pending', 'processing'].includes(task.status)" 
                                        variant="ghost" size="icon" @click="cancelTask(task.id)" :title="t('importTasks.list.cancelTask')">
                                        <Ban class="h-4 w-4 text-orange-500" />
                                    </Button>

                                    <!-- Actions for Failed/Cancelled -->
                                    <Button v-if="['failed', 'cancelled'].includes(task.status)" 
                                        variant="ghost" size="icon" @click="retryTask(task.id)" :title="t('common.retry')">
                                        <RefreshCw class="h-4 w-4 text-blue-500" />
                                    </Button>

                                    <!-- Actions for Completed -->
                                    <Button v-if="task.status === 'completed'" 
                                        variant="ghost" size="icon" as-child :title="t('importTasks.list.viewQuestions')">
                                        <NuxtLink :to="`/questions?import_task_id=${task.id}`">
                                            <ExternalLink class="h-4 w-4 text-green-600" />
                                        </NuxtLink>
                                    </Button>

                                    <!-- Delete (Always available) -->
                                    <Button variant="ghost" size="icon" @click="deleteTask(task.id)" :title="t('importTasks.list.deleteRecord')">
                                        <Trash2 class="h-4 w-4 text-muted-foreground hover:text-destructive" />
                                    </Button>
                                </div>
                            </TableCell>
                        </TableRow>
                    </TableBody>
                </Table>

                <!-- Pagination -->
                <div v-if="total > 0" class="flex justify-center mt-4 pb-4">
                  <Pagination v-model:page="page" :total="total" :sibling-count="1" show-edges :default-page="1"
                    :items-per-page="pageSize">
                    <PaginationContent v-slot="{ items }" class="flex items-center gap-1">
                      <PaginationFirst />
                      <PaginationPrevious />
                      <template v-for="(item, index) in items">
                        <PaginationItem v-if="item.type === 'page'" :key="index" :value="item.value" as-child>
                          <Button class="w-10 h-10 p-0" :variant="item.value === page ? 'default' : 'outline'">
                            {{ item.value }}
                          </Button>
                        </PaginationItem>
                        <PaginationEllipsis v-else :key="item.type" :index="index" />
                      </template>
                      <PaginationNext />
                      <PaginationLast />
                    </PaginationContent>
                  </Pagination>
                </div>
            </CardContent>
        </Card>
        <ImportTaskDuplicatesDialog v-model:open="duplicatesOpen" :duplicates="duplicatesOf" />
    </div>
</template>
