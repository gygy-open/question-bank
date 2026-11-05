<script setup lang="ts">
/**
 * 「整组替换」对话框(规格 §12.3 N2):列出其他题中条件类型组合相同的元素组,选一个替换进来,
 * AI 改写题目并校验,生成一道草稿变式题。
 */
import { ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import { Loader2 } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import MathText from '@/components/structure/MathText.vue'
import StructComposeJobStatus from '@/components/structure/StructComposeJobStatus.vue'
import { getApiErrorDetail } from '@/lib/apiErrors'
import { cn } from '@/lib/utils'
import type { StructElementGroup, StructGroupCandidate } from '~/types'

const props = defineProps<{ group: StructElementGroup | null, members: string[] }>()
const open = defineModel<boolean>('open', { default: false })

const { t } = useI18n()
const api = useStructure()

const candidates = ref<StructGroupCandidate[]>([])
const loading = ref(false)
const picked = ref<number | null>(null)
const submitting = ref(false)
const jobId = ref<number | null>(null)

async function load(): Promise<void> {
  if (!props.group) return
  loading.value = true
  try {
    candidates.value = (await api.groupCandidates(props.group.id)).items
  } catch (e) {
    toast.error(t('structure.panel.loadFailed'), { description: getApiErrorDetail(e, '') })
  } finally {
    loading.value = false
  }
}

async function submit(): Promise<void> {
  if (!props.group || picked.value == null) return
  submitting.value = true
  try {
    jobId.value = (await api.replaceGroup(props.group.id, picked.value)).job_id
  } catch (e) {
    toast.error(t('structure.compose.failed'), { description: getApiErrorDetail(e, '') })
  } finally {
    submitting.value = false
  }
}

watch(open, (value) => {
  if (!value) return
  picked.value = null
  jobId.value = null
  candidates.value = []
  void load()
})
</script>

<template>
  <Dialog v-model:open="open">
    <DialogContent class="sm:max-w-2xl">
      <DialogHeader>
        <DialogTitle>{{ t('structure.groups.replaceTitle', { name: group?.name ?? '' }) }}</DialogTitle>
        <DialogDescription>{{ t('structure.groups.replaceHint') }}</DialogDescription>
      </DialogHeader>
      <div v-if="jobId == null" class="space-y-3">
        <div class="rounded-md border bg-muted/30 px-3 py-2 text-sm">
          <div class="mb-1 text-xs text-muted-foreground">{{ t('structure.groups.current') }}</div>
          <p v-for="(text, i) in members" :key="i"><MathText :text="text" /></p>
        </div>
        <div v-if="loading" class="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 class="h-4 w-4 animate-spin" />{{ t('common.loading') }}</div>
        <p v-else-if="!candidates.length" class="text-sm text-muted-foreground">{{ t('structure.groups.noCandidates') }}</p>
        <div class="max-h-80 space-y-2 overflow-y-auto">
          <button
            v-for="candidate in candidates"
            :key="candidate.group_id"
            type="button"
            :class="cn('block w-full rounded-md border px-3 py-2 text-left text-sm hover:bg-accent', picked === candidate.group_id && 'border-primary bg-primary/5')"
            @click="picked = candidate.group_id"
          >
            <div class="mb-1 text-xs text-muted-foreground">#{{ candidate.question_id }} · {{ candidate.name }}</div>
            <p v-for="(text, i) in candidate.contents" :key="i"><MathText :text="text" /></p>
          </button>
        </div>
      </div>
      <StructComposeJobStatus v-else :job-id="jobId" @open="open = false" />
      <DialogFooter>
        <Button variant="outline" @click="open = false">{{ jobId == null ? t('common.cancel') : t('common.close') }}</Button>
        <Button v-if="jobId == null" :disabled="picked == null || submitting" @click="submit">
          <Loader2 v-if="submitting" class="mr-2 h-4 w-4 animate-spin" />{{ t('structure.groups.replace') }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
