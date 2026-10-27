<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowRight, Loader2, Music } from '@lucide/vue'
import { toast } from 'vue-sonner'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { useMedia, type MediaAssetListItem, type MediaReferences, type MediaReplaceResult } from '@/composables/useMedia'
import { getApiErrorDetail } from '@/lib/apiErrors'
import { mediaName, mediaOwnerLabel, referenceKey, replaceableReferences, replaceSummary } from '@/lib/mediaLibrary'

const open = defineModel<boolean>('open', { required: true })
const props = defineProps<{
    asset: MediaAssetListItem
    replacement: { assetId: number; src: string; title?: string | null } | null
    references: MediaReferences | null
}>()
const emit = defineEmits<{ replaced: [result: MediaReplaceResult] }>()

const { t } = useI18n()
const { replaceMedia } = useMedia()
const scope = ref<'all' | 'some'>('all')
const chosen = ref(new Set<string>())
const submitting = ref(false)

const candidates = computed(() => replaceableReferences(props.references?.items ?? []))
const noun = computed(() => t(props.asset.kind === 'audio' ? 'mediaPicker.noun.audio' : 'mediaPicker.noun.image'))
const frozenCount = computed(() => (props.references?.items ?? []).filter(item => item.owner_type === 'composition_version').length)
const canSubmit = computed(() => !!props.replacement && !submitting.value && (scope.value === 'all' ? candidates.value.length > 0 : chosen.value.size > 0))

watch(open, (isOpen) => {
    if (!isOpen) return
    scope.value = 'all'
    chosen.value = new Set(candidates.value.map(referenceKey))
})

function toggle(key: string, value: boolean | 'indeterminate') {
    const next = new Set(chosen.value)
    if (value === true) next.add(key)
    else next.delete(key)
    chosen.value = next
}

async function submit() {
    if (!props.replacement || !canSubmit.value) return
    submitting.value = true
    try {
        const targets = scope.value === 'all'
            ? undefined
            : candidates.value
                .filter(item => chosen.value.has(referenceKey(item)))
                .map(({ owner_type, owner_id }) => ({ owner_type, owner_id }))
        const result = await replaceMedia(props.asset.id, props.replacement.assetId, targets)
        toast.success(replaceSummary(result))
        emit('replaced', result)
        open.value = false
    } catch (error) {
        toast.error(getApiErrorDetail(error, t('media.replace.failed')))
    } finally {
        submitting.value = false
    }
}
</script>

<template>
    <Dialog v-model:open="open">
        <DialogContent class="sm:max-w-lg">
            <DialogHeader>
                <DialogTitle>{{ t(props.asset.kind === 'audio' ? 'media.replace.title.audio' : 'media.replace.title.image') }}</DialogTitle>
                <DialogDescription>{{ t('media.replace.description', { noun }) }}</DialogDescription>
            </DialogHeader>

            <div class="flex items-center justify-center gap-3">
                <div class="flex size-28 items-center justify-center overflow-hidden rounded border bg-muted" :title="mediaName(asset)">
                    <Music v-if="asset.kind === 'audio'" class="size-8 text-muted-foreground" />
                    <img v-else-if="asset.displayable" :src="asset.url" :alt="t('media.replace.originalAlt')" class="max-h-full max-w-full object-contain" />
                </div>
                <ArrowRight class="size-5 shrink-0 text-muted-foreground" />
                <div class="flex size-28 items-center justify-center overflow-hidden rounded border bg-muted" :title="replacement?.title ?? ''">
                    <Music v-if="asset.kind === 'audio'" class="size-8 text-muted-foreground" />
                    <img v-else-if="replacement" :src="replacement.src" :alt="t('media.replace.newAlt')" class="max-h-full max-w-full object-contain" />
                </div>
            </div>

            <RadioGroup v-model="scope" class="gap-2">
                <label class="flex items-start gap-2 text-sm">
                    <RadioGroupItem value="all" class="mt-0.5" />
                    <span>{{ t('media.replace.scopeAll', { count: candidates.length }) }}</span>
                </label>
                <label class="flex items-start gap-2 text-sm">
                    <RadioGroupItem value="some" class="mt-0.5" />
                    <span>{{ t('media.replace.scopeSome') }}</span>
                </label>
            </RadioGroup>
            <ul v-if="scope === 'some'" class="max-h-48 space-y-1.5 overflow-y-auto rounded border p-2 text-sm">
                <li v-for="item in candidates" :key="referenceKey(item)">
                    <label class="flex items-center gap-2">
                        <Checkbox :model-value="chosen.has(referenceKey(item))" @update:model-value="(v) => toggle(referenceKey(item), v)" />
                        <span class="shrink-0 text-xs text-muted-foreground">{{ mediaOwnerLabel(item.owner_type) }}</span>
                        <span class="truncate">{{ item.title }}</span>
                    </label>
                </li>
            </ul>

            <ul class="space-y-1 text-xs text-muted-foreground">
                <li v-if="frozenCount">{{ t('media.replace.frozenNote', { count: frozenCount }) }}</li>
                <li v-if="references?.hidden_count">{{ t('media.replace.hiddenNote', { count: references.hidden_count }) }}</li>
                <li>{{ t('media.replace.concurrentNote') }}</li>
            </ul>

            <DialogFooter>
                <Button variant="outline" @click="open = false">{{ t('common.cancel') }}</Button>
                <Button :disabled="!canSubmit" @click="submit">
                    <Loader2 v-if="submitting" class="mr-2 size-4 animate-spin" />{{ t('media.replace.confirm') }}
                </Button>
            </DialogFooter>
        </DialogContent>
    </Dialog>
</template>
