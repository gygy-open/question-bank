<script setup lang="ts">
import { computed, onActivated, ref, watch } from 'vue'
import { AlertCircle, ChevronLeft, ChevronRight, Download, ImageOff, LayoutGrid, List, Loader2, Music, RotateCw, Tag, Trash2, Upload, X } from '@lucide/vue'
import { toast } from 'vue-sonner'
import PageHeader from '@/components/PageHeader.vue'
import ClearableInput from '@/components/ClearableInput.vue'
import ClearableSelect from '@/components/ClearableSelect.vue'
import MediaDetailSheet from '@/components/media/MediaDetailSheet.vue'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { useMedia, useMediaBatch, type MediaAssetListItem, type MediaListQuery } from '@/composables/useMedia'
import { getApiErrorDetail } from '@/lib/apiErrors'
import { formatBytes, mediaDimension, mediaFormat, mediaName } from '@/lib/mediaLibrary'

const PAGE_SIZE = 40

const { currentSubjectId } = useSubjectContext()
const { can } = usePermissions()
const canEdit = computed(() => can(Capability.EDIT_QUESTION, currentSubjectId.value))
const { listSubjectMedia, uploadContentImage } = useMedia()
const { batchDelete, batchUpdateSource, archiveUrl } = useMediaBatch()

const view = ref<'grid' | 'list'>('grid')
const keyword = ref('')
const usage = ref<string | undefined>('0')
const kindFilter = ref<string | undefined>('0')
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
// 批量选择只在当前页内有效，翻页或重新加载时清空。
const checked = ref(new Set<number>())
const batchBusy = ref(false)
const sourceDialogOpen = ref(false)
const batchSource = ref('')
const allChecked = computed(() => items.value.length > 0 && items.value.every(item => checked.value.has(item.id)))

function toggleChecked(id: number, value: boolean | 'indeterminate') {
    const next = new Set(checked.value)
    if (value === true) next.add(id)
    else next.delete(id)
    checked.value = next
}

function toggleAll(value: boolean | 'indeterminate') {
    checked.value = value === true ? new Set(items.value.map(item => item.id)) : new Set()
}

async function runBatch(action: () => Promise<{ affected: number; skipped: number }>, verb: string, skipReason: string) {
    batchBusy.value = true
    try {
        const { affected, skipped } = await action()
        toast.success(skipped ? `已${verb} ${affected} 张，${skipped} 张${skipReason}` : `已${verb} ${affected} 张`)
        await load()
    } catch (error) {
        toast.error(getApiErrorDetail(error, `${verb}失败`))
    } finally {
        batchBusy.value = false
    }
}

function deleteChecked() {
    const sid = currentSubjectId.value
    if (!sid || !confirm(`删除所选 ${checked.value.size} 个文件中未被使用的？仍被引用的会保留。`)) return
    runBatch(() => batchDelete(sid, [...checked.value]), '删除', '仍被使用已保留')
}

async function saveBatchSource() {
    const sid = currentSubjectId.value
    if (!sid) return
    sourceDialogOpen.value = false
    await runBatch(() => batchUpdateSource(sid, [...checked.value], batchSource.value.trim() || null), '更新', '未更新')
}

function downloadChecked() {
    const sid = currentSubjectId.value
    if (!sid) return
    const link = document.createElement('a')
    link.href = archiveUrl(sid, [...checked.value])
    link.download = ''
    link.click()
}

const pages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))
const hasFilters = computed(() => !!keyword.value.trim() || (!!usage.value && usage.value !== '0') || (!!kindFilter.value && kindFilter.value !== '0'))

const kindOptions = [
    { label: '全部', value: '0' },
    { label: '图片', value: 'image' },
    { label: '音频', value: 'audio' },
]

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
            kind: kindFilter.value === 'image' || kindFilter.value === 'audio' ? kindFilter.value : undefined,
            used: usage.value === 'used' ? true : usage.value === 'unused' ? false : undefined,
            sort: sort.value,
            page: page.value,
            size: PAGE_SIZE,
        })
        items.value = res.items
        total.value = res.total
        checked.value = new Set()
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
watch([usage, kindFilter, sort, currentSubjectId], () => {
    if (page.value !== 1) page.value = 1
    else load()
})
watch(page, load)
// 页面被 keepalive 缓存；编辑器等处的上传需要在返回时刷新。
onActivated(load)

function clearFilters() {
    keyword.value = ''
    usage.value = '0'
    kindFilter.value = '0'
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
    toggleChecked(id, false)
    if (items.value.length === 0 && page.value > 1) page.value--
}

async function uploadFiles(files: FileList | File[] | null | undefined) {
    const sid = currentSubjectId.value
    const list = Array.from(files ?? []).filter((file) => file.type.startsWith('image/') || file.type.startsWith('audio/'))
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
        toast.success(`已上传 ${ok} 个文件（与库中相同的文件会直接复用）`)
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
    <input ref="fileInputRef" type="file" multiple accept="image/png,image/jpeg,image/gif,image/webp,audio/mpeg,audio/mp4,audio/x-m4a,audio/ogg,audio/wav,audio/x-wav,.mp3,.m4a,.ogg,.wav" class="hidden" @change="onFileChange" />

    <main
        class="flex flex-1 flex-col gap-5 px-4 py-6"
        :class="dragOver ? 'outline-2 outline-dashed outline-primary -outline-offset-4' : ''"
        @dragover.prevent="dragOver = canEdit"
        @dragleave.self="dragOver = false"
        @drop.prevent="onDrop"
    >
        <p class="text-sm text-muted-foreground">本学科题目、材料题与稿件中使用的图片和音频。编辑器里插入时可以直接从这里选择。</p>

        <div class="grid gap-3 bg-muted/40 p-4 sm:grid-cols-[2fr_1fr_1fr_1fr_auto] sm:items-end">
            <div class="space-y-2">
                <Label class="text-xs">搜索</Label>
                <ClearableInput v-model="keyword" placeholder="文件名或替代文本" />
            </div>
            <div class="space-y-2">
                <Label class="text-xs">类型</Label>
                <ClearableSelect v-model="kindFilter" :options="kindOptions" />
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
                <Button v-if="canEdit" size="sm" @click="fileInputRef?.click()"><Upload class="mr-2 size-4" />上传文件</Button>
            </template>
        </div>

        <div v-else-if="view === 'grid'" class="grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-6">
            <div v-for="item in items" :key="item.id" class="group relative">
                <button
                    type="button"
                    class="flex w-full flex-col gap-1.5 rounded-md border p-2 text-left transition-colors hover:border-primary focus-visible:outline-2 focus-visible:outline-primary"
                    :class="checked.has(item.id) ? 'border-primary' : ''"
                    @click="openDetail(item)"
                >
                    <div class="flex aspect-square flex-col items-center justify-center gap-1 overflow-hidden rounded bg-muted">
                        <template v-if="item.kind === 'audio'">
                            <Music class="size-8 text-muted-foreground" />
                            <span class="text-xs text-muted-foreground">{{ mediaDimension(item) }}</span>
                        </template>
                        <img v-else-if="item.displayable" :src="item.url" :alt="item.alt || item.original_filename || ''" loading="lazy" class="max-h-full max-w-full object-contain" />
                        <ImageOff v-else class="size-6 text-muted-foreground" />
                    </div>
                    <span class="truncate text-sm">{{ mediaName(item) }}</span>
                    <span class="flex flex-wrap gap-x-2 text-xs">
                        <span :class="item.usage_count ? 'text-muted-foreground' : 'text-muted-foreground/60'">{{ usageLabel(item.usage_count) }}</span>
                        <span v-if="!item.displayable" class="text-amber-600">无法预览</span>
                        <span v-else-if="item.kind === 'image' && !item.alt" class="text-muted-foreground/60">缺 alt</span>
                    </span>
                </button>
                <Checkbox
                    class="absolute left-3 top-3 bg-background transition-opacity"
                    :class="checked.size ? 'opacity-100' : 'opacity-0 group-hover:opacity-100 focus-visible:opacity-100'"
                    :model-value="checked.has(item.id)"
                    :aria-label="`选择 ${mediaName(item)}`"
                    @update:model-value="(v) => toggleChecked(item.id, v)"
                />
            </div>
        </div>

        <table v-else class="w-full text-sm">
            <thead class="border-b text-left text-xs text-muted-foreground">
                <tr>
                    <th class="w-8 py-2 font-normal"><Checkbox :model-value="allChecked" aria-label="全选本页" @update:model-value="toggleAll" /></th>
                    <th class="w-16 py-2 font-normal">预览</th>
                    <th class="py-2 font-normal">名称</th>
                    <th class="hidden py-2 font-normal sm:table-cell">格式</th>
                    <th class="hidden py-2 font-normal md:table-cell">尺寸 / 时长</th>
                    <th class="py-2 font-normal">大小</th>
                    <th class="py-2 font-normal">使用</th>
                    <th class="hidden py-2 font-normal md:table-cell">上传时间</th>
                </tr>
            </thead>
            <tbody>
                <tr v-for="item in items" :key="item.id" class="cursor-pointer border-b hover:bg-muted/50" tabindex="0" @click="openDetail(item)" @keydown.enter="openDetail(item)">
                    <td class="py-1.5" @click.stop>
                        <Checkbox :model-value="checked.has(item.id)" :aria-label="`选择 ${mediaName(item)}`" @update:model-value="(v) => toggleChecked(item.id, v)" />
                    </td>
                    <td class="py-1.5">
                        <div class="flex size-12 items-center justify-center overflow-hidden rounded bg-muted">
                            <Music v-if="item.kind === 'audio'" class="size-4 text-muted-foreground" />
                            <img v-else-if="item.displayable" :src="item.url" :alt="item.alt || item.original_filename || ''" loading="lazy" class="max-h-full max-w-full object-contain" />
                            <ImageOff v-else class="size-4 text-muted-foreground" />
                        </div>
                    </td>
                    <td class="max-w-64 truncate py-1.5">{{ mediaName(item) }}</td>
                    <td class="hidden py-1.5 text-muted-foreground sm:table-cell">{{ mediaFormat(item.mime) }}</td>
                    <td class="hidden py-1.5 text-muted-foreground md:table-cell">{{ mediaDimension(item) }}</td>
                    <td class="py-1.5 text-muted-foreground">{{ formatBytes(item.byte_size) }}</td>
                    <td class="py-1.5" :class="item.usage_count ? '' : 'text-muted-foreground/60'">{{ usageLabel(item.usage_count) }}</td>
                    <td class="hidden py-1.5 text-muted-foreground md:table-cell">{{ new Date(item.created_at).toLocaleDateString() }}</td>
                </tr>
            </tbody>
        </table>

        <div v-if="checked.size" class="sticky bottom-4 z-10 flex flex-wrap items-center gap-2 rounded-md border bg-background p-2 shadow-md">
            <span class="px-2 text-sm">已选 {{ checked.size }} 张</span>
            <Button variant="ghost" size="sm" @click="toggleAll(!allChecked)">{{ allChecked ? '取消全选' : '全选本页' }}</Button>
            <div class="ml-auto flex flex-wrap gap-2">
                <Button variant="outline" size="sm" @click="downloadChecked"><Download class="mr-2 size-4" />下载</Button>
                <template v-if="canEdit">
                    <Button variant="outline" size="sm" :disabled="batchBusy" @click="batchSource = ''; sourceDialogOpen = true"><Tag class="mr-2 size-4" />设置来源</Button>
                    <Button variant="outline" size="sm" class="text-destructive" :disabled="batchBusy" @click="deleteChecked"><Trash2 class="mr-2 size-4" />删除未使用</Button>
                </template>
                <Button variant="ghost" size="icon" title="清除选择" aria-label="清除选择" @click="toggleAll(false)"><X class="size-4" /></Button>
            </div>
        </div>

        <div v-if="total > 0" class="flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
            <span>共 {{ total }} 个文件</span>
            <div class="flex items-center gap-2">
                <Button variant="outline" size="icon" :disabled="page <= 1 || loading" title="上一页" aria-label="上一页" @click="page--"><ChevronLeft class="size-4" /></Button>
                <span>第 {{ page }} / {{ pages }} 页</span>
                <Button variant="outline" size="icon" :disabled="page >= pages || loading" title="下一页" aria-label="下一页" @click="page++"><ChevronRight class="size-4" /></Button>
            </div>
        </div>
    </main>

    <MediaDetailSheet v-model:open="detailOpen" :asset="selected" :can-edit="canEdit" @updated="onUpdated" @deleted="onDeleted" @replaced="load" />

    <Dialog v-model:open="sourceDialogOpen">
        <DialogContent class="sm:max-w-md">
            <DialogHeader><DialogTitle>设置来源 / 版权</DialogTitle></DialogHeader>
            <form class="space-y-4" @submit.prevent="saveBatchSource">
                <div class="space-y-1.5">
                    <Label for="batch-source">应用到所选 {{ checked.size }} 个文件；留空则清除来源</Label>
                    <Input id="batch-source" v-model="batchSource" maxlength="255" />
                </div>
                <DialogFooter>
                    <Button type="button" variant="outline" @click="sourceDialogOpen = false">取消</Button>
                    <Button type="submit">保存</Button>
                </DialogFooter>
            </form>
        </DialogContent>
    </Dialog>
</template>
