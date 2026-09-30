<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Download, ExternalLink, ImageOff, Loader2, Trash2 } from '@lucide/vue'
import { toast } from 'vue-sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { useMedia, type MediaAssetListItem, type MediaReferences } from '@/composables/useMedia'
import { getApiErrorDetail } from '@/lib/apiErrors'
import { formatBytes, groupMediaReferences, mediaReferenceLink } from '@/lib/mediaLibrary'

const open = defineModel<boolean>('open', { required: true })
const props = defineProps<{ asset: MediaAssetListItem | null; canEdit: boolean }>()
const emit = defineEmits<{ updated: [asset: MediaAssetListItem]; deleted: [id: number] }>()

const { updateMedia, deleteMedia, getMediaReferences } = useMedia()

const form = ref({ original_filename: '', alt: '', source: '' })
const saving = ref(false)
const deleting = ref(false)
const references = ref<MediaReferences | null>(null)
const loadingRefs = ref(false)

const groups = computed(() => groupMediaReferences(references.value?.items ?? []))
const referenceCount = computed(() => (references.value?.items.length ?? 0) + (references.value?.hidden_count ?? 0))
const dirty = computed(() => {
    const a = props.asset
    if (!a) return false
    return form.value.original_filename !== (a.original_filename ?? '')
        || form.value.alt !== (a.alt ?? '')
        || form.value.source !== (a.source ?? '')
})

watch(() => [open.value, props.asset?.id] as const, async ([isOpen]) => {
    const a = props.asset
    if (!isOpen || !a) return
    form.value = { original_filename: a.original_filename ?? '', alt: a.alt ?? '', source: a.source ?? '' }
    references.value = null
    loadingRefs.value = true
    try {
        references.value = await getMediaReferences(a.id)
    } catch (error) {
        toast.error(getApiErrorDetail(error, '引用信息加载失败'))
    } finally {
        loadingRefs.value = false
    }
}, { immediate: true })

async function save() {
    const a = props.asset
    if (!a || saving.value) return
    saving.value = true
    try {
        const updated = await updateMedia(a.id, form.value)
        emit('updated', { ...a, ...updated })
        toast.success('已保存')
    } catch (error) {
        toast.error(getApiErrorDetail(error, '保存失败'))
    } finally {
        saving.value = false
    }
}

async function remove() {
    const a = props.asset
    if (!a || deleting.value || !confirm(`确定删除「${a.original_filename || `图片 #${a.id}`}」吗？`)) return
    deleting.value = true
    try {
        await deleteMedia(a.id)
        emit('deleted', a.id)
        open.value = false
        toast.success('图片已删除')
    } catch (error) {
        toast.error(getApiErrorDetail(error, '删除失败'))
    } finally {
        deleting.value = false
    }
}
</script>

<template>
    <Sheet v-model:open="open">
        <SheetContent side="right" class="w-full overflow-y-auto sm:max-w-md">
            <SheetHeader>
                <SheetTitle class="truncate">{{ asset?.original_filename || (asset ? `图片 #${asset.id}` : '') }}</SheetTitle>
                <SheetDescription>修改名称、替代文本与来源只影响资料信息，不改变文件本身。</SheetDescription>
            </SheetHeader>

            <div v-if="asset" class="space-y-6 px-4 pb-6">
                <div class="flex min-h-40 items-center justify-center overflow-hidden rounded-md border bg-muted">
                    <img v-if="asset.displayable" :src="asset.url" :alt="asset.alt || asset.original_filename || ''" class="max-h-72 max-w-full object-contain" />
                    <div v-else class="flex flex-col items-center gap-2 py-10 text-sm text-muted-foreground">
                        <ImageOff class="size-6" />
                        <span>浏览器无法显示此格式（{{ asset.mime }}），可下载原件查看</span>
                    </div>
                </div>

                <dl class="grid grid-cols-[5rem_1fr] gap-y-1 text-sm">
                    <dt class="text-muted-foreground">格式</dt><dd>{{ asset.mime }}</dd>
                    <template v-if="asset.width && asset.height">
                        <dt class="text-muted-foreground">尺寸</dt><dd>{{ asset.width }} × {{ asset.height }}</dd>
                    </template>
                    <dt class="text-muted-foreground">大小</dt><dd>{{ formatBytes(asset.byte_size) }}</dd>
                    <dt class="text-muted-foreground">上传时间</dt><dd>{{ new Date(asset.created_at).toLocaleString() }}</dd>
                </dl>

                <form class="space-y-3" @submit.prevent="save">
                    <div class="space-y-1.5">
                        <Label for="media-name">名称</Label>
                        <Input id="media-name" v-model="form.original_filename" :disabled="!canEdit" maxlength="255" />
                    </div>
                    <div class="space-y-1.5">
                        <Label for="media-alt">替代文本（alt）</Label>
                        <Input id="media-alt" v-model="form.alt" :disabled="!canEdit" maxlength="500" placeholder="描述图片内容，便于检索与无障碍阅读" />
                    </div>
                    <div class="space-y-1.5">
                        <Label for="media-source">来源 / 版权</Label>
                        <Input id="media-source" v-model="form.source" :disabled="!canEdit" maxlength="255" />
                    </div>
                    <Button v-if="canEdit" type="submit" size="sm" :disabled="!dirty || saving">
                        <Loader2 v-if="saving" class="mr-2 size-4 animate-spin" />保存
                    </Button>
                </form>

                <section class="space-y-2">
                    <h3 class="text-sm font-medium">被引用于</h3>
                    <div v-if="loadingRefs" class="flex justify-center py-4"><Loader2 class="size-5 animate-spin text-muted-foreground" /></div>
                    <p v-else-if="referenceCount === 0" class="text-sm text-muted-foreground">未被任何内容使用</p>
                    <template v-else>
                        <div v-for="group in groups" :key="group.type" class="space-y-1">
                            <p class="text-xs text-muted-foreground">{{ group.label }}（{{ group.items.length }}）</p>
                            <ul class="space-y-1 text-sm">
                                <li v-for="item in group.items" :key="`${item.owner_type}-${item.owner_id}`" class="flex items-center gap-2">
                                    <NuxtLink v-if="mediaReferenceLink(item)" :to="mediaReferenceLink(item)!" class="flex min-w-0 items-center gap-1 hover:underline">
                                        <span class="truncate">{{ item.title }}</span>
                                        <ExternalLink class="size-3 shrink-0" />
                                    </NuxtLink>
                                    <span v-else class="truncate text-muted-foreground">{{ item.title }}</span>
                                    <span v-if="item.deleted" class="shrink-0 text-xs text-muted-foreground">已删除</span>
                                    <span v-if="item.owner_type === 'composition_version'" class="shrink-0 text-xs text-muted-foreground">v{{ item.version_no }} · 已冻结</span>
                                </li>
                            </ul>
                        </div>
                        <p v-if="references?.hidden_count" class="text-xs text-muted-foreground">另有 {{ references.hidden_count }} 处你无权查看的内容</p>
                    </template>
                </section>

                <div class="flex flex-wrap gap-2 border-t pt-4">
                    <Button as-child variant="outline" size="sm">
                        <a :href="`${asset.url}?download=true`" download><Download class="mr-2 size-4" />下载原件</a>
                    </Button>
                    <Button
                        v-if="canEdit"
                        variant="outline"
                        size="sm"
                        class="text-destructive"
                        :disabled="deleting || loadingRefs || referenceCount > 0"
                        :title="referenceCount > 0 ? '仍被内容引用，需先从这些内容中移除后才能删除' : ''"
                        @click="remove"
                    >
                        <Trash2 class="mr-2 size-4" />删除
                    </Button>
                </div>
                <p v-if="canEdit && referenceCount > 0" class="text-xs text-muted-foreground">仍被内容引用的图片不能删除；已冻结的定稿版本会一直保留其引用。</p>
            </div>
        </SheetContent>
    </Sheet>
</template>
