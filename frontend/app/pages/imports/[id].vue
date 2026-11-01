<script setup lang="ts">
import { computed, onActivated, onDeactivated, onUnmounted, ref, watch } from 'vue'
import {
  AlertTriangle,
  ArrowLeft,
  Ban,
  Check,
  CheckCircle2,
  Loader2,
  Play,
  RefreshCw,
  Settings,
  Trash2,
  XCircle,
} from '@lucide/vue'
import { toast } from 'vue-sonner'
import { Button } from '@/components/ui/button'
import ImportReview from '@/components/import/ImportReview.vue'
import ImportTaskDuplicatesDialog from '@/components/dedup/ImportTaskDuplicatesDialog.vue'
import { getApiErrorDetail } from '@/lib/apiErrors'
import { createdCount, failureMessage } from '@/lib/importTasks'
import { formatDateTime } from '@/lib/locale'
import type { DuplicateCandidate } from '@/lib/questionDedup'
import { isActiveImport, type ImportTaskItem } from '@/composables/useImportQueue'

const { t } = useI18n()
const { $api } = useNuxtApp()
const route = useRoute()
const router = useRouter()
const queue = useImportQueue()

const id = computed(() => Number(route.params.id))
const task = ref<ImportTaskItem | null>(null)
const missing = ref(false)
const busy = ref(false)

const load = async () => {
  if (!id.value) return
  try {
    const data = await $api<ImportTaskItem>(`/imports/${id.value}`)
    if (data.id !== id.value) return
    task.value = data
    missing.value = false
    queue.upsert(data)
  } catch {
    task.value = null
    missing.value = true
  }
}

// 进行中的导入每 2 秒刷新一次进度;其余状态只在操作后刷新。
let timer: ReturnType<typeof setInterval> | null = null
const stopPolling = () => {
  if (timer) clearInterval(timer)
  timer = null
}
const syncPolling = () => {
  const active = !!task.value && isActiveImport(task.value)
  if (active && !timer) timer = setInterval(load, 2000)
  if (!active) stopPolling()
}
watch(task, syncPolling)
watch(id, () => {
  task.value = null
  load()
}, { immediate: true })
onActivated(() => {
  load()
  syncPolling()
})
onDeactivated(stopPolling)
onUnmounted(stopPolling)

const run = async (action: () => Promise<unknown>, success?: string) => {
  busy.value = true
  try {
    await action()
    if (success) toast.success(success)
    await load()
    await queue.refresh()
  } catch (e: any) {
    toast.error(getApiErrorDetail(e, e.message))
  } finally {
    busy.value = false
  }
}

const cancel = () => {
  if (!confirm(t('imports.detail.cancelConfirm'))) return
  run(() => $api<unknown>(`/imports/${id.value}/cancel`, { method: 'POST' }), t('imports.detail.cancelled'))
}
const retry = () => run(() => $api<unknown>(`/imports/${id.value}/retry`, { method: 'POST' }), t('imports.detail.retried'))
const resume = () => run(() => $api<unknown>('/imports/resume', { method: 'POST', body: { ids: [id.value] } }), t('imports.detail.resumed'))
const remove = async () => {
  if (!confirm(t('imports.detail.deleteConfirm'))) return
  busy.value = true
  try {
    await $api<unknown>(`/imports/${id.value}`, { method: 'DELETE' })
    toast.success(t('imports.detail.deleted'))
    queue.remove(id.value)
    await queue.refreshSummary()
    router.replace('/imports')
  } catch (e: any) {
    toast.error(getApiErrorDetail(e, e.message))
  } finally {
    busy.value = false
  }
}

const onReviewDone = async () => {
  await load()
  await queue.refresh()
}

// --- 进度 ---
const STAGES = ['parsing', 'extracting', 'matching'] as const
const usesAi = computed(() => task.value?.progress?.method !== 'structured')
const visibleStages = computed(() => (usesAi.value ? STAGES : (['parsing', 'extracting'] as const)))
const stageIndex = computed(() => {
  const stage = task.value?.progress?.stage
  const index = visibleStages.value.findIndex((s) => s === stage)
  return task.value?.status === 'pending' ? -1 : Math.max(index, 0)
})

// --- 已完成 ---
const summary = computed<Record<string, any>>(() => {
  try {
    return task.value?.result_summary ? JSON.parse(task.value.result_summary) : {}
  } catch {
    return {}
  }
})
const duplicates = computed<Record<string, DuplicateCandidate[]>>(() => summary.value.duplicates ?? {})
const duplicateCount = computed(() => Object.keys(duplicates.value).length)
const duplicatesOpen = ref(false)
const compositionLink = computed(() => summary.value.composition_id
  ? `/compositions/${summary.value.composition_scope ?? 'personal'}/${summary.value.composition_id}`
  : null)

const methodLabel = computed(() => {
  const method = task.value?.progress?.method ?? (task.value?.method !== 'auto' ? task.value?.method : null)
  return method ? t(`imports.detail.methods.${method}`) : null
})
const failure = computed(() => (task.value ? failureMessage(task.value) : null))
</script>

<template>
  <div class="mx-auto w-full max-w-5xl space-y-4 p-4">
    <NuxtLink to="/imports" class="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground md:hidden">
      <ArrowLeft class="h-4 w-4" />{{ t('imports.detail.back') }}
    </NuxtLink>

    <div v-if="missing" class="py-16 text-center text-sm text-muted-foreground">
      {{ t('apiErrors.import_task.not_found') }}
    </div>

    <div v-else-if="!task" class="flex justify-center py-16">
      <Loader2 class="h-5 w-5 animate-spin text-muted-foreground" />
    </div>

    <template v-else>
      <header class="space-y-1">
        <h1 class="break-all text-lg font-semibold">{{ task.original_filename }}</h1>
        <p class="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
          <span>{{ formatDateTime(task.created_at.endsWith('Z') ? task.created_at : `${task.created_at}Z`) }}</span>
          <span v-if="methodLabel">{{ methodLabel }}</span>
          <span v-if="task.progress?.method !== 'structured'">{{ task.mode === 'solve' ? t('imports.detail.modeSolve') : t('imports.detail.modeExtract') }}</span>
          <span v-if="task.auto_commit">{{ t('imports.detail.autoCommit') }}</span>
          <span v-if="task.owner_name">{{ task.owner_name }}</span>
        </p>
      </header>

      <!-- 排队 / 识别中 -->
      <section v-if="task.status === 'pending' || task.status === 'processing'" class="rounded-xl border p-6">
        <div class="flex items-center gap-3">
          <Loader2 class="h-5 w-5 animate-spin text-primary" />
          <div>
            <p class="font-medium">{{ task.status === 'pending' ? t('imports.detail.queuedTitle') : t('imports.detail.processingTitle') }}</p>
            <p class="text-sm text-muted-foreground">
              {{ task.status === 'pending'
                ? (task.queue_ahead ? t('imports.detail.queuedAhead', { count: task.queue_ahead }) : t('imports.detail.queuedNext'))
                : t('imports.detail.processingHint') }}
            </p>
          </div>
        </div>
        <ol class="mt-6 space-y-3">
          <li v-for="(stage, index) in visibleStages" :key="stage" class="flex items-center gap-3 text-sm">
            <span
              class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-xs"
              :class="index < stageIndex ? 'border-primary bg-primary text-primary-foreground' : index === stageIndex ? 'border-primary text-primary' : 'text-muted-foreground'"
            >
              <Check v-if="index < stageIndex" class="h-3.5 w-3.5" />
              <Loader2 v-else-if="index === stageIndex" class="h-3.5 w-3.5 animate-spin" />
              <template v-else>{{ index + 1 }}</template>
            </span>
            <span :class="index <= stageIndex ? 'text-foreground' : 'text-muted-foreground'">{{ t(`imports.stages.${stage}`) }}</span>
          </li>
        </ol>
        <div class="mt-6 flex justify-end">
          <Button variant="outline" :disabled="busy" @click="cancel">
            <Ban class="mr-2 h-4 w-4" />{{ t('imports.detail.cancel') }}
          </Button>
        </div>
      </section>

      <!-- 已暂停 -->
      <section v-else-if="task.status === 'paused'" class="rounded-xl border border-amber-500/40 bg-amber-500/5 p-6">
        <div class="flex gap-3">
          <AlertTriangle class="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
          <div class="min-w-0 space-y-1">
            <p class="font-medium">{{ t('imports.detail.pausedTitle') }}</p>
            <p class="text-sm text-muted-foreground">{{ t(`imports.detail.pausedReasons.${task.paused_reason ?? 'unavailable'}`) }}</p>
            <details v-if="task.error_message" class="text-xs text-muted-foreground">
              <summary class="cursor-pointer">{{ t('imports.detail.errorDetail') }}</summary>
              <pre class="mt-2 whitespace-pre-wrap break-all">{{ task.error_message }}</pre>
            </details>
          </div>
        </div>
        <div class="mt-4 flex flex-wrap justify-end gap-2">
          <Button variant="ghost" :disabled="busy" @click="cancel">{{ t('imports.detail.cancel') }}</Button>
          <Button v-if="task.paused_reason === 'auth' || task.paused_reason === 'model'" variant="outline" as-child>
            <NuxtLink to="/settings"><Settings class="mr-2 h-4 w-4" />{{ t('imports.paused.openSettings') }}</NuxtLink>
          </Button>
          <Button :disabled="busy" @click="resume">
            <Play class="mr-2 h-4 w-4" />{{ t('imports.detail.resume') }}
          </Button>
        </div>
      </section>

      <!-- 失败 / 已取消 -->
      <section v-else-if="task.status === 'failed' || task.status === 'cancelled'" class="rounded-xl border p-6" :class="task.status === 'failed' ? 'border-destructive/40 bg-destructive/5' : ''">
        <div class="flex gap-3">
          <XCircle v-if="task.status === 'failed'" class="mt-0.5 h-5 w-5 shrink-0 text-destructive" />
          <Ban v-else class="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground" />
          <div class="min-w-0 space-y-1">
            <p class="font-medium">{{ task.status === 'failed' ? t('imports.detail.failedTitle') : t('imports.detail.cancelledTitle') }}</p>
            <p v-if="task.status === 'failed' && failure" class="text-sm text-muted-foreground">{{ t(failure.key, failure.params ?? {}) }}</p>
            <details v-if="task.status === 'failed' && task.error_message" class="text-xs text-muted-foreground">
              <summary class="cursor-pointer">{{ t('imports.detail.errorDetail') }}</summary>
              <pre class="mt-2 whitespace-pre-wrap break-all">{{ task.error_message }}</pre>
            </details>
          </div>
        </div>
        <div class="mt-4 flex flex-wrap justify-end gap-2">
          <Button variant="ghost" :disabled="busy" @click="remove">
            <Trash2 class="mr-2 h-4 w-4" />{{ t('imports.detail.delete') }}
          </Button>
          <Button :disabled="busy" @click="retry">
            <RefreshCw class="mr-2 h-4 w-4" />{{ t('imports.detail.retry') }}
          </Button>
        </div>
      </section>

      <!-- 待审核 -->
      <ImportReview
        v-else-if="task.status === 'review_ready'"
        :key="task.id"
        :task="task"
        @committed="onReviewDone"
        @discarded="onReviewDone"
      />

      <!-- 已完成 -->
      <section v-else-if="task.status === 'completed'" class="flex flex-col items-center space-y-4 rounded-xl border py-10 text-center">
        <div class="rounded-full bg-green-100 p-3 dark:bg-green-900/20">
          <CheckCircle2 class="h-10 w-10 text-green-600 dark:text-green-400" />
        </div>
        <div class="space-y-1">
          <h2 class="text-xl font-semibold">{{ t('importSmart.success.title') }}</h2>
          <p class="text-sm text-muted-foreground">{{ t('imports.detail.completedDescription', { count: createdCount(task) }) }}</p>
        </div>
        <p v-if="summary.composition_title" class="rounded-lg border bg-muted/40 px-4 py-2 text-sm">
          {{ t('importSmart.success.composition', { title: summary.composition_title }) }}
        </p>
        <div v-if="summary.skipped?.length" class="w-full max-w-xl rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-left text-sm">
          <p class="mb-2 font-medium">{{ t('importSmart.success.skipped', { count: summary.skipped.length }) }}</p>
          <ul class="list-disc space-y-1 pl-5 text-muted-foreground">
            <li v-for="(s, i) in summary.skipped" :key="i">{{ s.message }}</li>
          </ul>
        </div>
        <div v-if="summary.degraded?.length" class="w-full max-w-xl rounded-lg border p-4 text-left text-sm">
          <p class="mb-2 font-medium">{{ t('importSmart.success.degraded') }}</p>
          <ul class="list-disc space-y-1 pl-5 text-muted-foreground">
            <li v-for="(d, i) in summary.degraded" :key="i">{{ t('importSmart.success.degradedItem', { reason: d.reason, excerpt: d.excerpt }) }}</li>
          </ul>
        </div>
        <div class="flex flex-wrap justify-center gap-3">
          <Button v-if="compositionLink" as-child>
            <NuxtLink :to="compositionLink">{{ t('importSmart.success.openComposition') }}</NuxtLink>
          </Button>
          <Button as-child :variant="compositionLink ? 'outline' : 'default'">
            <NuxtLink :to="`/questions?import_task_id=${task.id}`">{{ t('importSmart.success.viewImported') }}</NuxtLink>
          </Button>
          <Button v-if="duplicateCount" variant="outline" @click="duplicatesOpen = true">
            {{ t('imports.detail.viewDuplicates', { count: duplicateCount }) }}
          </Button>
        </div>
        <ImportTaskDuplicatesDialog v-model:open="duplicatesOpen" :duplicates="duplicates" @deleted="load" />
      </section>
    </template>
  </div>
</template>
