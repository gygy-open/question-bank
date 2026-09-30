<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ImageOff, Loader2, Search, Upload } from '@lucide/vue'
import { toast } from 'vue-sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useImageUpload, type UploadedImageAttrs } from '@/components/rich-editor/useImageUpload'
import { useMedia, useMediaSubject, type MediaAssetListItem } from '@/composables/useMedia'
import { loadRecentMedia, rememberRecentMedia, type RecentMediaEntry } from '@/lib/recentMedia'

const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ select: [attrs: UploadedImageAttrs] }>()

const PAGE_SIZE = 30

const subjectId = useMediaSubject()
const { uploadImage } = useImageUpload()
const { listSubjectMedia } = useMedia()

const tab = ref<'upload' | 'library' | 'recent'>('library')
const query = ref('')
const items = ref<MediaAssetListItem[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const uploading = ref(false)
const dragOver = ref(false)
const recent = ref<RecentMediaEntry[]>([])
const fileInputRef = ref<HTMLInputElement | null>(null)

const hasMore = computed(() => items.value.length < total.value)

async function fetchLibrary(reset: boolean) {
    const sid = subjectId.value
    if (!sid) return
    loading.value = true
    try {
        const nextPage = reset ? 1 : page.value + 1
        const res = await listSubjectMedia(sid, { q: query.value.trim() || undefined, page: nextPage, size: PAGE_SIZE })
        items.value = reset ? res.items : [...items.value, ...res.items]
        total.value = res.total
        page.value = nextPage
    } catch {
        toast.error('媒体库加载失败')
    } finally {
        loading.value = false
    }
}

watch(open, async (value) => {
    if (!value) return
    const sid = subjectId.value
    recent.value = sid ? loadRecentMedia(sid) : []
    query.value = ''
    tab.value = 'library'
    await fetchLibrary(true)
    if (total.value === 0) tab.value = 'upload'
})

let searchTimer: ReturnType<typeof setTimeout> | undefined
watch(query, () => {
    clearTimeout(searchTimer)
    searchTimer = setTimeout(() => fetchLibrary(true), 300)
})

function choose(entry: RecentMediaEntry) {
    if (subjectId.value) rememberRecentMedia(subjectId.value, entry)
    emit('select', { src: entry.url, assetId: entry.id })
    open.value = false
}

async function uploadFile(file: File | undefined) {
    if (!file || uploading.value) return
    if (!file.type.startsWith('image/')) {
        toast.error('请选择图片文件')
        return
    }
    uploading.value = true
    try {
        const attrs = await uploadImage(file)
        if (attrs) {
            emit('select', attrs)
            open.value = false
        }
    } finally {
        uploading.value = false
    }
}

function onFileChange(event: Event) {
    const input = event.target as HTMLInputElement
    uploadFile(input.files?.[0])
    input.value = ''
}

function onDrop(event: DragEvent) {
    dragOver.value = false
    uploadFile(event.dataTransfer?.files?.[0])
}

function usageLabel(count: number) {
    return count > 0 ? `${count} 处使用` : '未使用'
}
</script>

<template>
    <Dialog v-model:open="open">
        <DialogContent class="w-[95vw] sm:max-w-[760px]">
            <DialogHeader>
                <DialogTitle>插入图片</DialogTitle>
                <DialogDescription>上传新图片，或从本学科媒体库中选择已有图片。</DialogDescription>
            </DialogHeader>

            <p v-if="!subjectId" class="py-8 text-center text-sm text-muted-foreground">请先选择学科再插入图片。</p>

            <Tabs v-else v-model="tab" class="mt-2">
                <TabsList class="grid w-full grid-cols-3">
                    <TabsTrigger value="upload">上传</TabsTrigger>
                    <TabsTrigger value="library">媒体库</TabsTrigger>
                    <TabsTrigger value="recent">最近使用</TabsTrigger>
                </TabsList>

                <TabsContent value="upload" class="mt-3">
                    <button
                        type="button"
                        class="flex h-64 w-full flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed text-sm text-muted-foreground transition-colors hover:border-primary hover:text-foreground"
                        :class="dragOver ? 'border-primary bg-primary/5 text-foreground' : ''"
                        :disabled="uploading"
                        @click="fileInputRef?.click()"
                        @dragover.prevent="dragOver = true"
                        @dragleave="dragOver = false"
                        @drop.prevent="onDrop"
                    >
                        <Loader2 v-if="uploading" class="size-6 animate-spin" />
                        <Upload v-else class="size-6" />
                        <span>{{ uploading ? '上传中…' : '点击选择或拖入图片' }}</span>
                        <span class="text-xs">支持 PNG、JPEG、GIF、WebP，单张不超过 10 MB</span>
                    </button>
                    <input ref="fileInputRef" type="file" accept="image/png,image/jpeg,image/gif,image/webp" class="hidden" @change="onFileChange" />
                </TabsContent>

                <TabsContent value="library" class="mt-3 space-y-3">
                    <div class="relative">
                        <Search class="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                        <Input v-model="query" placeholder="按文件名或替代文本搜索" class="pl-8" />
                    </div>
                    <div class="max-h-[55vh] overflow-y-auto">
                        <p v-if="!loading && items.length === 0" class="py-12 text-center text-sm text-muted-foreground">
                            {{ query ? '没有匹配的图片' : '媒体库还是空的，先上传一张吧' }}
                        </p>
                        <div class="grid grid-cols-3 gap-3 sm:grid-cols-5">
                            <button
                                v-for="item in items"
                                :key="item.id"
                                type="button"
                                class="group flex flex-col gap-1 rounded-md border p-1.5 text-left transition-colors hover:border-primary disabled:cursor-not-allowed disabled:opacity-60"
                                :disabled="!item.displayable"
                                :title="item.displayable ? item.original_filename ?? '' : '浏览器无法显示此格式'"
                                @click="choose({ id: item.id, url: item.url, name: item.original_filename })"
                            >
                                <div class="flex aspect-square items-center justify-center overflow-hidden rounded bg-muted">
                                    <img v-if="item.displayable" :src="item.url" :alt="item.original_filename ?? ''" loading="lazy" class="max-h-full max-w-full object-contain" />
                                    <ImageOff v-else class="size-6 text-muted-foreground" />
                                </div>
                                <span class="truncate text-xs">{{ item.original_filename || `图片 #${item.id}` }}</span>
                                <span class="text-[11px]" :class="item.usage_count ? 'text-muted-foreground' : 'text-muted-foreground/60'">{{ usageLabel(item.usage_count) }}</span>
                            </button>
                        </div>
                        <div v-if="loading" class="flex justify-center py-4"><Loader2 class="size-5 animate-spin text-muted-foreground" /></div>
                        <div v-else-if="hasMore" class="flex justify-center pt-3">
                            <Button variant="outline" size="sm" @click="fetchLibrary(false)">加载更多</Button>
                        </div>
                    </div>
                </TabsContent>

                <TabsContent value="recent" class="mt-3">
                    <p v-if="recent.length === 0" class="py-12 text-center text-sm text-muted-foreground">还没有插入过图片</p>
                    <div v-else class="grid max-h-[55vh] grid-cols-3 gap-3 overflow-y-auto sm:grid-cols-5">
                        <button
                            v-for="entry in recent"
                            :key="entry.id"
                            type="button"
                            class="flex flex-col gap-1 rounded-md border p-1.5 text-left transition-colors hover:border-primary"
                            @click="choose(entry)"
                        >
                            <div class="flex aspect-square items-center justify-center overflow-hidden rounded bg-muted">
                                <img :src="entry.url" :alt="entry.name ?? ''" loading="lazy" class="max-h-full max-w-full object-contain" />
                            </div>
                            <span class="truncate text-xs">{{ entry.name || `图片 #${entry.id}` }}</span>
                        </button>
                    </div>
                </TabsContent>
            </Tabs>
        </DialogContent>
    </Dialog>
</template>
