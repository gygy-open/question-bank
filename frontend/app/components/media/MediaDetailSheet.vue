<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Copy, Download, ExternalLink, ImageOff, Loader2, Replace, Trash2 } from '@lucide/vue'
import { toast } from 'vue-sonner'
import MediaPickerDialog from '@/components/media/MediaPickerDialog.vue'
import MediaReplaceDialog from '@/components/media/MediaReplaceDialog.vue'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { useMedia, useMediaBatch, type MediaAssetListItem, type MediaReferences } from '@/composables/useMedia'
import type { UploadedImageAttrs } from '@/components/rich-editor/useImageUpload'
import { getApiErrorDetail } from '@/lib/apiErrors'
import { formatDateTime } from '@/lib/locale'
import { formatBytes, groupMediaReferences, mediaDimension, mediaFormat, mediaName, mediaReferenceLink, replaceableReferences } from '@/lib/mediaLibrary'

const open = defineModel<boolean>('open', { required: true })
const props = defineProps<{ asset: MediaAssetListItem | null; canEdit: boolean }>()
const emit = defineEmits<{ updated: [asset: MediaAssetListItem]; deleted: [id: number]; replaced: [] }>()

const { t } = useI18n()
const { updateMedia, deleteMedia, getMediaReferences } = useMedia()

const form = ref({ original_filename: '', alt: '', source: '' })
const saving = ref(false)
const deleting = ref(false)
const references = ref<MediaReferences | null>(null)
const loadingRefs = ref(false)

const groups = computed(() => groupMediaReferences(references.value?.items ?? []))
const referenceCount = computed(() => (references.value?.items.length ?? 0) + (references.value?.hidden_count ?? 0))
const replaceableCount = computed(() => replaceableReferences(references.value?.items ?? []).length)
const pickerOpen = ref(false)
const replaceOpen = ref(false)
const replacement = ref<UploadedImageAttrs | null>(null)

function onPicked(attrs: UploadedImageAttrs) {
    if (attrs.assetId === props.asset?.id) {
        toast.info(t('media.detail.pickAnother'))
        return
    }
    replacement.value = attrs
    replaceOpen.value = true
}

function onReplaced() {
    emit('replaced')
    open.value = false
}

const { subjects } = useSubjectContext()
const { can } = usePermissions()
const { copyToSubject } = useMediaBatch()
const copyTargets = computed(() => subjects.value.filter(s => s.id !== props.asset?.subject_id && can(Capability.EDIT_QUESTION, s.id)))

async function copyTo(subject: { id: number; name: string }) {
    if (!props.asset) return
    try {
        await copyToSubject(props.asset.id, subject.id)
        toast.success(t('media.detail.copiedTo', { name: subject.name }))
    } catch (error) {
        toast.error(getApiErrorDetail(error, t('media.detail.copyFailed')))
    }
}
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
        toast.error(getApiErrorDetail(error, t('media.detail.referencesLoadFailed')))
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
        toast.success(t('common.saved'))
    } catch (error) {
        toast.error(getApiErrorDetail(error, t('common.saveFailed')))
    } finally {
        saving.value = false
    }
}

async function remove() {
    const a = props.asset
    if (!a || deleting.value || !confirm(t('media.detail.deleteConfirm', { name: mediaName(a) }))) return
    deleting.value = true
    try {
        await deleteMedia(a.id)
        emit('deleted', a.id)
        open.value = false
        toast.success(t('media.detail.deleted'))
    } catch (error) {
        toast.error(getApiErrorDetail(error, t('common.deleteFailed')))
    } finally {
        deleting.value = false
    }
}
</script>

<template>
    <Sheet v-model:open="open">
        <SheetContent side="right" class="w-full overflow-y-auto sm:max-w-md">
            <SheetHeader>
                <SheetTitle class="truncate">{{ asset ? mediaName(asset) : '' }}</SheetTitle>
                <SheetDescription>{{ t('media.detail.description') }}</SheetDescription>
            </SheetHeader>

            <div v-if="asset" class="space-y-6 px-4 pb-6">
                <audio v-if="asset.kind === 'audio'" :src="asset.url" controls preload="metadata" class="w-full" />
                <div v-else class="flex min-h-40 items-center justify-center overflow-hidden rounded-md border bg-muted">
                    <img v-if="asset.displayable" :src="asset.url" :alt="asset.alt || asset.original_filename || ''" class="max-h-72 max-w-full object-contain" />
                    <div v-else class="flex flex-col items-center gap-2 py-10 text-sm text-muted-foreground">
                        <ImageOff class="size-6" />
                        <span>{{ t('media.detail.unsupportedFormat', { mime: asset.mime }) }}</span>
                    </div>
                </div>

                <dl class="grid grid-cols-[5rem_1fr] gap-y-1 text-sm">
                    <dt class="text-muted-foreground">{{ t('media.columns.format') }}</dt><dd>{{ mediaFormat(asset.mime) }}</dd>
                    <template v-if="mediaDimension(asset) !== '—'">
                        <dt class="text-muted-foreground">{{ asset.kind === 'audio' ? t('media.detail.duration') : t('media.detail.dimension') }}</dt><dd>{{ mediaDimension(asset) }}</dd>
                    </template>
                    <dt class="text-muted-foreground">{{ t('media.columns.size') }}</dt><dd>{{ formatBytes(asset.byte_size) }}</dd>
                    <dt class="text-muted-foreground">{{ t('media.columns.uploadedAt') }}</dt><dd>{{ formatDateTime(asset.created_at) }}</dd>
                </dl>

                <form class="space-y-3" @submit.prevent="save">
                    <div class="space-y-1.5">
                        <Label for="media-name">{{ t('common.name') }}</Label>
                        <Input id="media-name" v-model="form.original_filename" :disabled="!canEdit" maxlength="255" />
                    </div>
                    <div class="space-y-1.5">
                        <Label for="media-alt">{{ t('media.detail.alt') }}</Label>
                        <Input id="media-alt" v-model="form.alt" :disabled="!canEdit" maxlength="500" :placeholder="t('media.detail.altPlaceholder')" />
                    </div>
                    <div class="space-y-1.5">
                        <Label for="media-source">{{ t('media.detail.source') }}</Label>
                        <Input id="media-source" v-model="form.source" :disabled="!canEdit" maxlength="255" />
                    </div>
                    <Button v-if="canEdit" type="submit" size="sm" :disabled="!dirty || saving">
                        <Loader2 v-if="saving" class="mr-2 size-4 animate-spin" />{{ t('common.save') }}
                    </Button>
                </form>

                <section class="space-y-2">
                    <h3 class="text-sm font-medium">{{ t('media.detail.referencedIn') }}</h3>
                    <div v-if="loadingRefs" class="flex justify-center py-4"><Loader2 class="size-5 animate-spin text-muted-foreground" /></div>
                    <p v-else-if="referenceCount === 0" class="text-sm text-muted-foreground">{{ t('media.detail.notReferenced') }}</p>
                    <template v-else>
                        <div v-for="group in groups" :key="group.type" class="space-y-1">
                            <p class="text-xs text-muted-foreground">{{ t('media.detail.groupLabel', { label: group.label, count: group.items.length }) }}</p>
                            <ul class="space-y-1 text-sm">
                                <li v-for="item in group.items" :key="`${item.owner_type}-${item.owner_id}`" class="flex items-center gap-2">
                                    <NuxtLink v-if="mediaReferenceLink(item)" :to="mediaReferenceLink(item)!" class="flex min-w-0 items-center gap-1 hover:underline">
                                        <span class="truncate">{{ item.title }}</span>
                                        <ExternalLink class="size-3 shrink-0" />
                                    </NuxtLink>
                                    <span v-else class="truncate text-muted-foreground">{{ item.title }}</span>
                                    <span v-if="item.deleted" class="shrink-0 text-xs text-muted-foreground">{{ t('media.detail.ownerDeleted') }}</span>
                                    <span v-if="item.owner_type === 'composition_version'" class="shrink-0 text-xs text-muted-foreground">{{ t('media.detail.frozenVersion', { version: item.version_no }) }}</span>
                                </li>
                            </ul>
                        </div>
                        <p v-if="references?.hidden_count" class="text-xs text-muted-foreground">{{ t('media.detail.hiddenCount', { count: references.hidden_count }) }}</p>
                    </template>
                </section>

                <div class="flex flex-wrap gap-2 border-t pt-4">
                    <Button as-child variant="outline" size="sm">
                        <a :href="`${asset.url}?download=true`" download><Download class="mr-2 size-4" />{{ t('media.detail.downloadOriginal') }}</a>
                    </Button>
                    <Button
                        v-if="canEdit"
                        variant="outline"
                        size="sm"
                        :disabled="loadingRefs || replaceableCount === 0"
                        :title="replaceableCount === 0 ? t('media.detail.noReplaceable') : ''"
                        @click="pickerOpen = true"
                    >
                        <Replace class="mr-2 size-4" />{{ t('media.detail.replace') }}
                    </Button>
                    <DropdownMenu v-if="copyTargets.length">
                        <DropdownMenuTrigger as-child>
                            <Button variant="outline" size="sm"><Copy class="mr-2 size-4" />{{ t('media.detail.copyToSubject') }}</Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="start">
                            <DropdownMenuLabel class="text-xs font-normal text-muted-foreground">{{ t('media.detail.copyToSubjectHint') }}</DropdownMenuLabel>
                            <DropdownMenuItem v-for="subject in copyTargets" :key="subject.id" @select="copyTo(subject)">{{ subject.name }}</DropdownMenuItem>
                        </DropdownMenuContent>
                    </DropdownMenu>
                    <Button
                        v-if="canEdit"
                        variant="outline"
                        size="sm"
                        class="text-destructive"
                        :disabled="deleting || loadingRefs || referenceCount > 0"
                        :title="referenceCount > 0 ? t('media.detail.deleteBlocked') : ''"
                        @click="remove"
                    >
                        <Trash2 class="mr-2 size-4" />{{ t('common.delete') }}
                    </Button>
                </div>
                <p v-if="canEdit && referenceCount > 0" class="text-xs text-muted-foreground">{{ t('media.detail.deleteBlockedHint') }}</p>
            </div>
        </SheetContent>
    </Sheet>
    <template v-if="asset && canEdit">
        <MediaPickerDialog v-model:open="pickerOpen" :kind="asset.kind" @select="onPicked" />
        <MediaReplaceDialog v-model:open="replaceOpen" :asset="asset" :replacement="replacement" :references="references" @replaced="onReplaced" />
    </template>
</template>
