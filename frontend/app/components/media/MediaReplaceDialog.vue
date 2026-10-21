<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowRight, Loader2 } from '@lucide/vue'
import { toast } from 'vue-sonner'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { useMedia, type MediaAssetListItem, type MediaReferences, type MediaReplaceResult } from '@/composables/useMedia'
import { getApiErrorDetail } from '@/lib/apiErrors'
import { MEDIA_OWNER_LABELS, referenceKey, replaceableReferences, replaceSummary } from '@/lib/mediaLibrary'

const open = defineModel<boolean>('open', { required: true })
const props = defineProps<{
    asset: MediaAssetListItem
    replacement: { assetId: number; src: string } | null
    references: MediaReferences | null
}>()
const emit = defineEmits<{ replaced: [result: MediaReplaceResult] }>()

const { replaceMedia } = useMedia()
const scope = ref<'all' | 'some'>('all')
const chosen = ref(new Set<string>())
const submitting = ref(false)

const candidates = computed(() => replaceableReferences(props.references?.items ?? []))
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
        toast.error(getApiErrorDetail(error, '替换失败'))
    } finally {
        submitting.value = false
    }
}
</script>

<template>
    <Dialog v-model:open="open">
        <DialogContent class="sm:max-w-lg">
            <DialogHeader>
                <DialogTitle>替换图片</DialogTitle>
                <DialogDescription>把所选内容里的这张图换成新图片。原图仍保留在媒体库中。</DialogDescription>
            </DialogHeader>

            <div class="flex items-center justify-center gap-3">
                <div class="flex size-28 items-center justify-center overflow-hidden rounded border bg-muted">
                    <img v-if="asset.displayable" :src="asset.url" alt="原图" class="max-h-full max-w-full object-contain" />
                </div>
                <ArrowRight class="size-5 shrink-0 text-muted-foreground" />
                <div class="flex size-28 items-center justify-center overflow-hidden rounded border bg-muted">
                    <img v-if="replacement" :src="replacement.src" alt="新图片" class="max-h-full max-w-full object-contain" />
                </div>
            </div>

            <RadioGroup v-model="scope" class="gap-2">
                <label class="flex items-start gap-2 text-sm">
                    <RadioGroupItem value="all" class="mt-0.5" />
                    <span>全部引用（{{ candidates.length }} 处）</span>
                </label>
                <label class="flex items-start gap-2 text-sm">
                    <RadioGroupItem value="some" class="mt-0.5" />
                    <span>只替换勾选的内容</span>
                </label>
            </RadioGroup>
            <ul v-if="scope === 'some'" class="max-h-48 space-y-1.5 overflow-y-auto rounded border p-2 text-sm">
                <li v-for="item in candidates" :key="referenceKey(item)">
                    <label class="flex items-center gap-2">
                        <Checkbox :model-value="chosen.has(referenceKey(item))" @update:model-value="(v) => toggle(referenceKey(item), v)" />
                        <span class="shrink-0 text-xs text-muted-foreground">{{ MEDIA_OWNER_LABELS[item.owner_type] }}</span>
                        <span class="truncate">{{ item.title }}</span>
                    </label>
                </li>
            </ul>

            <ul class="space-y-1 text-xs text-muted-foreground">
                <li v-if="frozenCount">{{ frozenCount }} 个已定稿版本不受影响，仍显示原图。</li>
                <li v-if="references?.hidden_count">另有 {{ references.hidden_count }} 处你无权查看的内容不会被替换。</li>
                <li>正在编辑这些内容的人保存时会提示内容已被修改。</li>
            </ul>

            <DialogFooter>
                <Button variant="outline" @click="open = false">取消</Button>
                <Button :disabled="!canSubmit" @click="submit">
                    <Loader2 v-if="submitting" class="mr-2 size-4 animate-spin" />确认替换
                </Button>
            </DialogFooter>
        </DialogContent>
    </Dialog>
</template>
