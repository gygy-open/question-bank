<script setup lang="ts">
import { computed, onActivated, ref, watch } from 'vue'
import { AlertCircle, ChevronLeft, ChevronRight, ImageOff, LayoutGrid, List, Loader2, RotateCw, Upload } from '@lucide/vue'
import { toast } from 'vue-sonner'
import PageHeader from '@/components/PageHeader.vue'
import ClearableInput from '@/components/ClearableInput.vue'
import ClearableSelect from '@/components/ClearableSelect.vue'
import MediaDetailSheet from '@/components/media/MediaDetailSheet.vue'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useMedia, type MediaAssetListItem, type MediaListQuery } from '@/composables/useMedia'
import { getApiErrorDetail } from '@/lib/apiErrors'
import { formatBytes } from '@/lib/mediaLibrary'

const PAGE_SIZE = 40

const { currentSubjectId } = useSubjectContext()
const { can } = usePermissions()
const canEdit = computed(() => can(Capability.EDIT_QUESTION, currentSubjectId.value))
const { listSubjectMedia, uploadContentImage } = useMedia()

const view = ref<'grid' | 'list'>('grid')
const keyword = ref('')
const usage = ref<string | undefined>('0')
const sort = ref<NonNullable<MediaListQuery['sort']>>('newest')
const page = ref(1)

const items = ref<MediaAssetListItem[]>([])
const total = ref(0)
const loading = ref(false)
const failed = ref(false)
const uploading = ref(false)
const dragOver = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)
const selected = ref<MediaAssetListItem | null>(null)
const detailOpen = ref(false)

const pages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))
const hasFilters = computed(() => !!keyword.value.trim() || (!!usage.value && usage.value !== '0'))

const usageOptions = [
    { label: '全部', value: '0' },
    { label: '已使用', value: 'used' },
    { label: '未使用', value: 'unused' },
]
const sortOptions = [
    { label: '最近上传', value: 'newest' },
    { label: '最早上传', value: 'oldest' },
    { label: '名称', value: 'name' },
    { label: '文件大小', value: 'size' },
]

async function load() {
    const sid = currentSubjectId.value
    if (!sid) return
    loading.value = true
    failed.value = false
    try {
        const res = await listSubjectMedia(sid, {
            q: keyword.value.trim() || undefined,
            used: usage.value === 'used' ? true : usage.value === 'unused' ? false : undefined,
            sort: sort.value,
            page: page.value,
            size: PAGE_SIZE,
        })
        items.value = res.items
        total.value = res.total
    } catch {
        failed.value = true
    } finally {
        loading.value = false
    }
}

let searchTimer: ReturnType<typeof setTimeout> | undefined
watch(keyword, () => {
    clearTimeout(searchTimer)
    searchTimer = setTimeout(() => {
        if (page.value !== 1) page.value = 1
        else load()
    }, 300)
})
watch([usage, sort, currentSubjectId], () => {
    if (page.value !== 1) page.value = 1
    else load()
})
watch(page, load)
// 页面被 keepalive 缓存；编辑器等处的上传需要在返回时刷新。
onActivated(load)

function clearFilters() {
    keyword.value = ''
    usage.value = '0'
}

function openDetail(item: MediaAssetListItem) {
    selected.value = item
    detailOpen.value = true
}

function onUpdated(asset: MediaAssetListItem) {
    items.value = items.value.map((item) => (item.id === asset.id ? asset : item))
    selected.value = asset
}

function onDeleted(id: number) {
    items.value = items.value.filter((item) => item.id !== id)
    total.value = Math.max(0, total.value - 1)
    if (items.value.length === 0 && page.value > 1) page.value--
}

async function uploadFiles(files: FileList | File[] | null | undefined) {
    const sid = currentSubjectId.value
    const list = Array.from(files ?? []).filter((file) => file.type.startsWith('image/'))
    if (!sid || list.length === 0 || uploading.value) return
    uploading.value = true
    let ok = 0
    for (const file of list) {
        try {
            await uploadContentImage(sid, file)
            ok++
        } catch (error) {
            toast.error(`${file.name}：${getApiErrorDetail(error, '上传失败')}`)
        }
    }
    uploading.value = false
    if (ok > 0) {
        toast.success(`已上传 ${ok} 张图片（与库中相同的文件会直接复用）`)
        if (page.value !== 1 || sort.value !== 'newest') {
            sort.value = 'newest'
            page.value = 1
        } else {
            await load()
        }
    }
}

function onFileChange(event: Event) {
    const input = event.target as HTMLInputElement
    uploadFiles(input.files)
    input.value = ''
}

function onDrop(event: DragEvent) {
    dragOver.value = false
    if (canEdit.value) uploadFiles(event.dataTransfer?.files)
}

function usageLabel(count: number) {
    return count > 0 ? `${count} 处使用` : '未使用'
}
</script>

<template>
    <PageHeader title="媒体库">
        <template #actions>
            <Button v-if="canEdit && currentSubjectId" size="sm" :disabled="uploading" @click="fileInputRef?.click()">
                <Loader2 v-if="uploading" class="mr-2 size-4 animate-spin" /><Upload v-else class="mr-2 size-4" />上传
            </Button>
        </template>
    </PageHeader>
    <input ref="fileInputRef" type="file" multiple accept="image/png,image/jpeg,image/gif,image/webp" class="hidden" @change="onFileChange" />

    <main
        class="flex flex-1 flex-col gap-5 px-4 py-6"
        :class="dragOver ? 'outline-2 outline-dashed outline-primary -outline-offset-4' : ''"
        @dragover.prevent="dragOver = canEdit"
        @dragleave.self="dragOver = false"
        @drop.prevent="onDrop"
    >
        <p class="text-sm text-muted-foreground">本学科题目、材料题与稿件中使用的图片。编辑器里插入图片时可以直接从这里选择。</p>

        <div class="grid gap-3 bg-muted/40 p-4 sm:grid-cols-[2fr_1fr_1fr_auto] sm:items-end">
            <div class="space-y-2">
                <Label class="text-xs">搜索</Label>
                <ClearableInput v-model="keyword" placeholder="文件名或替代文本" />
            </div>
            <div class="space-y-2">
                <Label class="text-xs">使用情况</Label>
                <ClearableSelect v-model="usage" :options="usageOptions" />
            </div>
            <div class="space-y-2">
                <Label class="text-xs">排序</Label>
                <Select v-model="sort">
                    <SelectTrigger class="w-full"><SelectValue /></SelectTrigger>
                    <SelectContent>
                        <SelectItem v-for="option in sortOptions" :key="option.value" :value="option.value">{{ option.label }}</SelectItem>
                    </SelectContent>
                </Select>
            </div>
            <ToggleGroup v-model="view" type="single" variant="outline" aria-label="视图">
                <ToggleGroupItem value="grid" aria-label="网格视图" title="网格视图"><LayoutGrid class="size-4" /></ToggleGroupItem>
                <ToggleGroupItem value="list" aria-label="列表视图" title="列表视图"><List class="size-4" /></ToggleGroupItem>
            </ToggleGroup>
        </div>

        <div v-if="!currentSubjectId" class="py-16 text-center text-sm text-muted-foreground">请先选择学科</div>
        <div v-else-if="loading && items.length === 0" class="flex justify-center py-16"><Loader2 class="size-7 animate-spin text-muted-foreground" /></div>
        <div v-else-if="failed" class="flex flex-col items-center gap-3 py-16 text-sm text-muted-foreground">
            <AlertCircle class="size-6" /><span>媒体库加载失败</span>
            <Button variant="outline" size="sm" @click="load"><RotateCw class="mr-2 size-4" />重试</Button>
        </div>
        <div v-else-if="items.length === 0" class="flex flex-col items-center gap-3 py-16 text-sm text-muted-foreground">
            <template v-if="hasFilters">
                <span>没有符合条件的图片</span>
                <Button variant="outline" size="sm" @click="clearFilters">清除筛选</Button>
            </template>
            <template v-else>
                <span>媒体库还是空的。题目中插入或导入文档时的图片会自动出现在这里。</span>
                <Button v-if="canEdit" size="sm" @click="fileInputRef?.click()"><Upload class="mr-2 size-4" />上传图片</Button>
            </template>
        </div>

        <div v-else-if="view === 'grid'" class="grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-6">
            <button
                v-for="item in items"
                :key="item.id"
                type="button"
                class="flex flex-col gap-1.5 rounded-md border p-2 text-left transition-colors hover:border-primary focus-visible:outline-2 focus-visible:outline-primary"
                @click="openDetail(item)"
            >
                <div class="flex aspect-square items-center justify-center overflow-hidden rounded bg-muted">
                    <img v-if="item.displayable" :src="item.url" :alt="item.alt || item.original_filename || ''" loading="lazy" class="max-h-full max-w-full object-contain" />
                    <ImageOff v-else class="size-6 text-muted-foreground" />
                </div>
                <span class="truncate text-sm">{{ item.original_filename || `图片 #${item.id}` }}</span>
                <span class="flex flex-wrap gap-x-2 text-xs">
                    <span :class="item.usage_count ? 'text-muted-foreground' : 'text-muted-foreground/60'">{{ usageLabel(item.usage_count) }}</span>
                    <span v-if="!item.displayable" class="text-amber-600">无法预览</span>
                    <span v-else-if="!item.alt" class="text-muted-foreground/60">缺 alt</span>
                </span>
            </button>
        </div>

        <table v-else class="w-full text-sm">
            <thead class="border-b text-left text-xs text-muted-foreground">
                <tr>
                    <th class="w-16 py-2 font-normal">预览</th>
                    <th class="py-2 font-normal">名称</th>
                    <th class="hidden py-2 font-normal sm:table-cell">格式</th>
                    <th class="hidden py-2 font-normal md:table-cell">尺寸</th>
                    <th class="py-2 font-normal">大小</th>
                    <th class="py-2 font-normal">使用</th>
                    <th class="hidden py-2 font-normal md:table-cell">上传时间</th>
                </tr>
            </thead>
            <tbody>
                <tr v-for="item in items" :key="item.id" class="cursor-pointer border-b hover:bg-muted/50" tabindex="0" @click="openDetail(item)" @keydown.enter="openDetail(item)">
                    <td class="py-1.5">
                        <div class="flex size-12 items-center justify-center overflow-hidden rounded bg-muted">
                            <img v-if="item.displayable" :src="item.url" :alt="item.alt || item.original_filename || ''" loading="lazy" class="max-h-full max-w-full object-contain" />
                            <ImageOff v-else class="size-4 text-muted-foreground" />
                        </div>
                    </td>
                    <td class="max-w-64 truncate py-1.5">{{ item.original_filename || `图片 #${item.id}` }}</td>
                    <td class="hidden py-1.5 text-muted-foreground sm:table-cell">{{ item.mime.replace('image/', '').toUpperCase() }}</td>
                    <td class="hidden py-1.5 text-muted-foreground md:table-cell">{{ item.width && item.height ? `${item.width}×${item.height}` : '—' }}</td>
                    <td class="py-1.5 text-muted-foreground">{{ formatBytes(item.byte_size) }}</td>
                    <td class="py-1.5" :class="item.usage_count ? '' : 'text-muted-foreground/60'">{{ usageLabel(item.usage_count) }}</td>
                    <td class="hidden py-1.5 text-muted-foreground md:table-cell">{{ new Date(item.created_at).toLocaleDateString() }}</td>
                </tr>
            </tbody>
        </table>

        <div v-if="total > 0" class="flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
            <span>共 {{ total }} 张图片</span>
            <div class="flex items-center gap-2">
                <Button variant="outline" size="icon" :disabled="page <= 1 || loading" title="上一页" aria-label="上一页" @click="page--"><ChevronLeft class="size-4" /></Button>
                <span>第 {{ page }} / {{ pages }} 页</span>
                <Button variant="outline" size="icon" :disabled="page >= pages || loading" title="下一页" aria-label="下一页" @click="page++"><ChevronRight class="size-4" /></Button>
            </div>
        </div>
    </main>

    <MediaDetailSheet v-model:open="detailOpen" :asset="selected" :can-edit="canEdit" @updated="onUpdated" @deleted="onDeleted" />
</template>
