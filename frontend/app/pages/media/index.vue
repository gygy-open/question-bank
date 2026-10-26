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
import { formatDate } from '@/lib/locale'
import { formatBytes, mediaDimension, mediaFormat, mediaName } from '@/lib/mediaLibrary'

const PAGE_SIZE = 40

const { t } = useI18n()

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

async function runBatch(action: () => Promise<{ affected: number; skipped: number }>, kind: 'delete' | 'update') {
    batchBusy.value = true
    try {
        const { affected, skipped } = await action()
        toast.success(skipped ? t(`media.batch.${kind}.partial`, { affected, skipped }) : t(`media.batch.${kind}.done`, { affected }))
        await load()
    } catch (error) {
        toast.error(getApiErrorDetail(error, t(`media.batch.${kind}.failed`)))
    } finally {
        batchBusy.value = false
    }
}

function deleteChecked() {
    const sid = currentSubjectId.value
    if (!sid || !confirm(t('media.batch.deleteConfirm', { count: checked.value.size }))) return
    runBatch(() => batchDelete(sid, [...checked.value]), 'delete')
}

async function saveBatchSource() {
    const sid = currentSubjectId.value
    if (!sid) return
    sourceDialogOpen.value = false
    await runBatch(() => batchUpdateSource(sid, [...checked.value], batchSource.value.trim() || null), 'update')
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

const kindOptions = computed(() => [
    { label: t('common.all'), value: '0' },
    { label: t('media.kind.image'), value: 'image' },
    { label: t('media.kind.audio'), value: 'audio' },
])

const usageOptions = computed(() => [
    { label: t('common.all'), value: '0' },
    { label: t('media.usage.used'), value: 'used' },
    { label: t('media.usage.unused'), value: 'unused' },
])
const sortOptions = computed(() => [
    { label: t('media.sort.newest'), value: 'newest' },
    { label: t('media.sort.oldest'), value: 'oldest' },
    { label: t('common.name'), value: 'name' },
    { label: t('media.sort.size'), value: 'size' },
])

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
            toast.error(t('media.uploadFileFailed', { name: file.name, error: getApiErrorDetail(error, t('common.uploadFailed')) }))
        }
    }
    uploading.value = false
    if (ok > 0) {
        toast.success(t('media.uploaded', { count: ok }))
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
    return count > 0 ? t('media.usageCount', { count }) : t('media.usage.unused')
}
</script>

<template>
    <PageHeader :title="t('nav.media')">
        <template #actions>
            <Button v-if="canEdit && currentSubjectId" size="sm" :disabled="uploading" @click="fileInputRef?.click()">
                <Loader2 v-if="uploading" class="mr-2 size-4 animate-spin" /><Upload v-else class="mr-2 size-4" />{{ t('media.upload') }}
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
        <p class="text-sm text-muted-foreground">{{ t('media.pageDescription') }}</p>

        <div class="grid gap-3 bg-muted/40 p-4 sm:grid-cols-[2fr_1fr_1fr_1fr_auto] sm:items-end">
            <div class="space-y-2">
                <Label class="text-xs">{{ t('media.filters.search') }}</Label>
                <ClearableInput v-model="keyword" :placeholder="t('media.filters.searchPlaceholder')" />
            </div>
            <div class="space-y-2">
                <Label class="text-xs">{{ t('media.filters.kind') }}</Label>
                <ClearableSelect v-model="kindFilter" :options="kindOptions" />
            </div>
            <div class="space-y-2">
                <Label class="text-xs">{{ t('media.filters.usage') }}</Label>
                <ClearableSelect v-model="usage" :options="usageOptions" />
            </div>
            <div class="space-y-2">
                <Label class="text-xs">{{ t('media.filters.sort') }}</Label>
                <Select v-model="sort">
                    <SelectTrigger class="w-full"><SelectValue /></SelectTrigger>
                    <SelectContent>
                        <SelectItem v-for="option in sortOptions" :key="option.value" :value="option.value">{{ option.label }}</SelectItem>
                    </SelectContent>
                </Select>
            </div>
            <ToggleGroup v-model="view" type="single" variant="outline" :aria-label="t('media.view.label')">
                <ToggleGroupItem value="grid" :aria-label="t('media.view.grid')" :title="t('media.view.grid')"><LayoutGrid class="size-4" /></ToggleGroupItem>
                <ToggleGroupItem value="list" :aria-label="t('media.view.list')" :title="t('media.view.list')"><List class="size-4" /></ToggleGroupItem>
            </ToggleGroup>
        </div>

        <div v-if="!currentSubjectId" class="py-16 text-center text-sm text-muted-foreground">{{ t('media.selectSubjectFirst') }}</div>
        <div v-else-if="loading && items.length === 0" class="flex justify-center py-16"><Loader2 class="size-7 animate-spin text-muted-foreground" /></div>
        <div v-else-if="failed" class="flex flex-col items-center gap-3 py-16 text-sm text-muted-foreground">
            <AlertCircle class="size-6" /><span>{{ t('media.loadFailed') }}</span>
            <Button variant="outline" size="sm" @click="load"><RotateCw class="mr-2 size-4" />{{ t('common.retry') }}</Button>
        </div>
        <div v-else-if="items.length === 0" class="flex flex-col items-center gap-3 py-16 text-sm text-muted-foreground">
            <template v-if="hasFilters">
                <span>{{ t('media.noMatch') }}</span>
                <Button variant="outline" size="sm" @click="clearFilters">{{ t('media.clearFilters') }}</Button>
            </template>
            <template v-else>
                <span>{{ t('media.empty') }}</span>
                <Button v-if="canEdit" size="sm" @click="fileInputRef?.click()"><Upload class="mr-2 size-4" />{{ t('media.uploadFiles') }}</Button>
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
                        <span v-if="!item.displayable" class="text-amber-600">{{ t('media.noPreview') }}</span>
                        <span v-else-if="item.kind === 'image' && !item.alt" class="text-muted-foreground/60">{{ t('media.missingAlt') }}</span>
                    </span>
                </button>
                <Checkbox
                    class="absolute left-3 top-3 bg-background transition-opacity"
                    :class="checked.size ? 'opacity-100' : 'opacity-0 group-hover:opacity-100 focus-visible:opacity-100'"
                    :model-value="checked.has(item.id)"
                    :aria-label="t('media.selectItem', { name: mediaName(item) })"
                    @update:model-value="(v) => toggleChecked(item.id, v)"
                />
            </div>
        </div>

        <table v-else class="w-full text-sm">
            <thead class="border-b text-left text-xs text-muted-foreground">
                <tr>
                    <th class="w-8 py-2 font-normal"><Checkbox :model-value="allChecked" :aria-label="t('media.selectPage')" @update:model-value="toggleAll" /></th>
                    <th class="w-16 py-2 font-normal">{{ t('media.columns.preview') }}</th>
                    <th class="py-2 font-normal">{{ t('common.name') }}</th>
                    <th class="hidden py-2 font-normal sm:table-cell">{{ t('media.columns.format') }}</th>
                    <th class="hidden py-2 font-normal md:table-cell">{{ t('media.columns.dimension') }}</th>
                    <th class="py-2 font-normal">{{ t('media.columns.size') }}</th>
                    <th class="py-2 font-normal">{{ t('media.columns.usage') }}</th>
                    <th class="hidden py-2 font-normal md:table-cell">{{ t('media.columns.uploadedAt') }}</th>
                </tr>
            </thead>
            <tbody>
                <tr v-for="item in items" :key="item.id" class="cursor-pointer border-b hover:bg-muted/50" tabindex="0" @click="openDetail(item)" @keydown.enter="openDetail(item)">
                    <td class="py-1.5" @click.stop>
                        <Checkbox :model-value="checked.has(item.id)" :aria-label="t('media.selectItem', { name: mediaName(item) })" @update:model-value="(v) => toggleChecked(item.id, v)" />
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
                    <td class="hidden py-1.5 text-muted-foreground md:table-cell">{{ formatDate(item.created_at) }}</td>
                </tr>
            </tbody>
        </table>

        <div v-if="checked.size" class="sticky bottom-4 z-10 flex flex-wrap items-center gap-2 rounded-md border bg-background p-2 shadow-md">
            <span class="px-2 text-sm">{{ t('media.selectedCount', { count: checked.size }) }}</span>
            <Button variant="ghost" size="sm" @click="toggleAll(!allChecked)">{{ allChecked ? t('media.deselectAll') : t('media.selectPage') }}</Button>
            <div class="ml-auto flex flex-wrap gap-2">
                <Button variant="outline" size="sm" @click="downloadChecked"><Download class="mr-2 size-4" />{{ t('common.download') }}</Button>
                <template v-if="canEdit">
                    <Button variant="outline" size="sm" :disabled="batchBusy" @click="batchSource = ''; sourceDialogOpen = true"><Tag class="mr-2 size-4" />{{ t('media.batch.setSource') }}</Button>
                    <Button variant="outline" size="sm" class="text-destructive" :disabled="batchBusy" @click="deleteChecked"><Trash2 class="mr-2 size-4" />{{ t('media.batch.deleteUnused') }}</Button>
                </template>
                <Button variant="ghost" size="icon" :title="t('media.clearSelection')" :aria-label="t('media.clearSelection')" @click="toggleAll(false)"><X class="size-4" /></Button>
            </div>
        </div>

        <div v-if="total > 0" class="flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
            <span>{{ t('media.total', { count: total }) }}</span>
            <div class="flex items-center gap-2">
                <Button variant="outline" size="icon" :disabled="page <= 1 || loading" :title="t('common.prevPage')" :aria-label="t('common.prevPage')" @click="page--"><ChevronLeft class="size-4" /></Button>
                <span>{{ t('media.pageIndicator', { page, pages }) }}</span>
                <Button variant="outline" size="icon" :disabled="page >= pages || loading" :title="t('common.nextPage')" :aria-label="t('common.nextPage')" @click="page++"><ChevronRight class="size-4" /></Button>
            </div>
        </div>
    </main>

    <MediaDetailSheet v-model:open="detailOpen" :asset="selected" :can-edit="canEdit" @updated="onUpdated" @deleted="onDeleted" @replaced="load" />

    <Dialog v-model:open="sourceDialogOpen">
        <DialogContent class="sm:max-w-md">
            <DialogHeader><DialogTitle>{{ t('media.batch.sourceDialogTitle') }}</DialogTitle></DialogHeader>
            <form class="space-y-4" @submit.prevent="saveBatchSource">
                <div class="space-y-1.5">
                    <Label for="batch-source">{{ t('media.batch.sourceDialogHint', { count: checked.size }) }}</Label>
                    <Input id="batch-source" v-model="batchSource" maxlength="255" />
                </div>
                <DialogFooter>
                    <Button type="button" variant="outline" @click="sourceDialogOpen = false">{{ t('common.cancel') }}</Button>
                    <Button type="submit">{{ t('common.save') }}</Button>
                </DialogFooter>
            </form>
        </DialogContent>
    </Dialog>
</template>
