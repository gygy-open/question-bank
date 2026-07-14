<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { Upload, FileText, CheckCircle, XCircle, Loader2, Ban, Trash2, RefreshCw, ExternalLink, AlertCircle, RotateCcw, Sparkles } from 'lucide-vue-next'
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
import { toast } from 'vue-sonner'

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
const queueStats = ref<QueueStats>({ pending: 0, processing: 0, completed: 0, failed: 0, cancelled: 0 })
const isUploading = ref(false)
const isDragging = ref(false)
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

const allSelected = computed(() => {
    return tasks.value.length > 0 && tasks.value.every(t => selectedTasks.value.includes(t.id))
})

const toggleSelectAll = (checked: boolean) => {
    if (checked) {
        selectedTasks.value = tasks.value.map(t => t.id)
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
    if (!confirm(`确定要重试选中的 ${selectedTasks.value.length} 个任务吗？`)) return

    let successCount = 0
    for (const taskId of selectedTasks.value) {
        try {
            await $api(`/imports/${taskId}/retry`, { method: 'POST' })
            successCount++
        } catch (e) {
            console.error(`Failed to retry task ${taskId}`, e)
        }
    }
    
    toast.success(`已重试 ${successCount} 个任务`)
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

        toast.success(`成功创建 ${data?.length || 0} 个导入任务`)
        page.value = 1 // Reset to first page
        await fetchTasks()
    } catch (e) {
        console.error(e)
        toast.error('上传失败', {
            description: String(e)
        })
    } finally {
        isUploading.value = false
    }
}

const cancelTask = async (taskId: number) => {
    if (!confirm('确定要取消此任务吗？')) return
    
    try {
        await $api(`/imports/${taskId}/cancel`, { method: 'POST' })
        toast.success('任务已取消')
        await fetchTasks()
    } catch (e) {
        toast.error('取消失败')
    }
}

const retryTask = async (taskId: number) => {
    try {
        await $api(`/imports/${taskId}/retry`, { method: 'POST' })
        toast.success('任务已重新加入队列')
        await fetchTasks()
    } catch (e) {
        toast.error('重试失败')
    }
}

const resetStuckTasks = async () => {
    if (!confirm('确定要重置所有处理中的任务吗？这会将它们重新设为等待状态。')) return
    
    try {
        const data: any = await $api('/imports/reset-stuck', { method: 'POST' })
        toast.success(`已重置 ${data.count} 个任务`)
        await fetchQueueStatus()
        await fetchTasks()
    } catch (e) {
        toast.error('重置失败')
    }
}

const deleteTask = async (taskId: number) => {
    if (!confirm('确定要删除此记录吗？')) return
    
    try {
        await $api(`/imports/${taskId}`, { method: 'DELETE' })
        toast.success('记录已删除')
        await fetchTasks()
    } catch (e) {
        toast.error('删除失败')
    }
}

const startPolling = () => {
    stopPolling()
    pollingInterval.value = setInterval(async () => {
        await fetchQueueStatus()
        const hasActive = tasks.value.some(t => ['pending', 'processing'].includes(t.status))
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

onMounted(() => {
    fetchQueueStatus()
    fetchTasks()
    startPolling()
})

onUnmounted(() => {
    stopPolling()
})

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

const statusLabel = (status: string) => {
    const map: Record<string, string> = {
        pending: '等待中',
        processing: '处理中',
        completed: '已完成',
        failed: '失败',
        cancelled: '已取消'
    }
    return map[status] || status
}

const getResultCount = (summaryJson?: string) => {
    if (!summaryJson) return 0
    try {
        const summary = JSON.parse(summaryJson)
        return summary.count || 0
    } catch (e) {
        return 0
    }
}
</script>

<template>
    <PageHeader title="异步导入队列">
        <template #actions>
            <Button v-if="selectedTasks.length > 0" variant="outline" @click="batchRetryTasks">
                <RefreshCw class="mr-2 h-4 w-4" />
                批量重试 ({{ selectedTasks.length }})
            </Button>
            <Button v-if="queueStats.processing > 0" variant="outline" @click="resetStuckTasks">
                <RotateCcw class="mr-2 h-4 w-4" />
                重置卡住任务
            </Button>
        </template>
    </PageHeader>

    <div class="py-6 space-y-8 px-4">
        <!-- Queue Stats -->
        <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
            <Card>
                <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle class="text-sm font-medium">等待中</CardTitle>
                    <Loader2 class="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                    <div class="text-2xl font-bold">{{ queueStats.pending }}</div>
                </CardContent>
            </Card>
            <Card>
                <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle class="text-sm font-medium">处理中</CardTitle>
                    <RefreshCw class="h-4 w-4 text-muted-foreground animate-spin" />
                </CardHeader>
                <CardContent>
                    <div class="text-2xl font-bold">{{ queueStats.processing }}</div>
                </CardContent>
            </Card>
            <Card>
                <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle class="text-sm font-medium">已完成</CardTitle>
                    <CheckCircle class="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                    <div class="text-2xl font-bold">{{ queueStats.completed }}</div>
                </CardContent>
            </Card>
            <Card>
                <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle class="text-sm font-medium">失败</CardTitle>
                    <XCircle class="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                    <div class="text-2xl font-bold">{{ queueStats.failed }}</div>
                </CardContent>
            </Card>
             <Card>
                <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle class="text-sm font-medium">已取消</CardTitle>
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
                <CardTitle>批量上传</CardTitle>
                <CardDescription>上传文件后，系统将在后台自动处理</CardDescription>
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

                <div class="border-2 border-dashed rounded-lg p-10 text-center transition-colors flex flex-col items-center justify-center min-h-[200px]"
                    :class="{ 
                        'opacity-50 pointer-events-none': isUploading,
                        'bg-muted/50 border-primary': isDragging,
                        'hover:bg-muted/50': !isDragging
                    }"
                    @dragover.prevent="handleDragOver"
                    @dragleave.prevent="handleDragLeave"
                    @drop.prevent="handleDrop">
                    <input type="file" multiple accept=".docx,.md" class="hidden" id="file-upload"
                        @change="handleFileChange" :disabled="isUploading">
                    <label for="file-upload"
                        class="cursor-pointer flex flex-col items-center gap-4 w-full h-full justify-center">
                        <div class="p-4 bg-primary/10 rounded-full">
                            <Upload class="h-10 w-10 text-primary" />
                        </div>
                        <div class="space-y-1">
                            <span class="text-lg font-medium block">点击选择文件 (支持多选)</span>
                            <span class="text-sm text-muted-foreground">支持拖拽上传，支持批量上传 .docx, .md 格式。上传文件后，系统将自动处理，不需要一直👀着。</span>
                        </div>
                    </label>
                    <div v-if="isUploading" class="mt-4 flex items-center text-sm text-muted-foreground">
                        <Loader2 class="mr-2 h-4 w-4 animate-spin" /> 正在上传...
                    </div>
                </div>
            </CardContent>
        </Card>

        <!-- Task List -->
        <Card>
            <CardHeader class="flex flex-row items-center justify-between">
                <div>
                    <CardTitle>导入队列</CardTitle>
                    <CardDescription>查看导入任务的处理状态和结果</CardDescription>
                </div>
                <div class="flex gap-2">
                    <div class="w-[180px]" v-if="currentUser?.is_superuser">
                        <Select v-model="userFilter">
                            <SelectTrigger>
                                <SelectValue placeholder="筛选用户" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">全部用户</SelectItem>
                                <SelectItem v-for="user in users" :key="user.id" :value="String(user.id)">
                                    {{ user.full_name || user.username }}
                                </SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    <div class="w-[180px]">
                        <Select v-model="statusFilter">
                            <SelectTrigger>
                                <SelectValue placeholder="筛选状态" />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">全部状态</SelectItem>
                                <SelectItem value="pending">等待中</SelectItem>
                                <SelectItem value="processing">处理中</SelectItem>
                                <SelectItem value="completed">已完成</SelectItem>
                                <SelectItem value="failed">失败</SelectItem>
                                <SelectItem value="cancelled">已取消</SelectItem>
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
                                <Checkbox :checked="allSelected" @update:model-value="toggleSelectAll" />
                            </TableHead>
                            <TableHead class="w-[300px]">文件名</TableHead>
                            <TableHead>所属用户</TableHead>
                            <TableHead>状态</TableHead>
                            <TableHead>结果</TableHead>
                            <TableHead>创建时间</TableHead>
                            <TableHead class="text-right">操作</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        <TableRow v-if="tasks.length === 0">
                            <TableCell colspan="7" class="text-center py-8 text-muted-foreground">
                                暂无导入任务
                            </TableCell>
                        </TableRow>
                        <TableRow v-for="task in tasks" :key="task.id">
                            <TableCell>
                                <Checkbox 
                                    :checked="selectedTasks.includes(task.id)" 
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
                                <div v-if="task.status === 'completed'" class="text-sm text-green-600 flex items-center gap-1">
                                    <CheckCircle class="h-3 w-3" />
                                    成功提取 {{ getResultCount(task.result_summary) }} 题
                                </div>
                                <div v-else-if="task.status === 'failed'" class="text-sm text-destructive flex items-center gap-1">
                                    <TooltipProvider>
                                        <Tooltip>
                                            <TooltipTrigger>
                                                <div class="flex items-center gap-1 cursor-help">
                                                    <AlertCircle class="h-3 w-3" />
                                                    <span>处理失败</span>
                                                </div>
                                            </TooltipTrigger>
                                            <TooltipContent>
                                                <p class="max-w-xs break-words">{{ task.error_message || '未知错误' }}</p>
                                            </TooltipContent>
                                        </Tooltip>
                                    </TooltipProvider>
                                </div>
                                <span v-else class="text-muted-foreground text-sm">-</span>
                            </TableCell>
                            <TableCell class="text-muted-foreground text-sm">
                                {{ new Date(task.created_at + 'Z').toLocaleString() }}
                            </TableCell>
                            <TableCell class="text-right">
                                <div class="flex justify-end gap-2">
                                    <!-- Actions for Pending/Processing -->
                                    <Button v-if="['pending', 'processing'].includes(task.status)" 
                                        variant="ghost" size="icon" @click="cancelTask(task.id)" title="取消任务">
                                        <Ban class="h-4 w-4 text-orange-500" />
                                    </Button>

                                    <!-- Actions for Failed/Cancelled -->
                                    <Button v-if="['failed', 'cancelled'].includes(task.status)" 
                                        variant="ghost" size="icon" @click="retryTask(task.id)" title="重试">
                                        <RefreshCw class="h-4 w-4 text-blue-500" />
                                    </Button>

                                    <!-- Actions for Completed -->
                                    <Button v-if="task.status === 'completed'" 
                                        variant="ghost" size="icon" as-child title="查看题目">
                                        <NuxtLink :to="`/questions?import_task_id=${task.id}`">
                                            <ExternalLink class="h-4 w-4 text-green-600" />
                                        </NuxtLink>
                                    </Button>

                                    <!-- Delete (Always available) -->
                                    <Button variant="ghost" size="icon" @click="deleteTask(task.id)" title="删除记录">
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
    </div>
</template>
