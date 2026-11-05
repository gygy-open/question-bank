<script setup lang="ts">
/**
 * 命题 / 组替换任务的进度与结果:每 2 秒轮询一次,成功时给出新题链接,失败时显示原因。
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { CircleCheck, Loader2, TriangleAlert } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import type { StructComposeJob } from '~/types'

const props = defineProps<{ jobId: number }>()
const emit = defineEmits<{ (e: 'open'): void }>()

const { t } = useI18n()
const api = useStructure()

const job = ref<StructComposeJob | null>(null)
let timer: ReturnType<typeof setTimeout> | null = null

const running = computed(() => !job.value || !['succeeded', 'failed', 'cancelled'].includes(job.value.status))
const failure = computed(() => {
  const j = job.value
  if (!j || j.status !== 'failed') return ''
  const code = j.progress.error_code
  const key = `structure.compose.errors.${code}`
  const reason = code ? t(key) : ''
  const detail = j.progress.problems?.length ? j.progress.problems.join('; ') : j.error ?? ''
  return [reason !== key ? reason : '', detail].filter(Boolean).join(t('structure.variant.reasonSeparator'))
})

async function poll(): Promise<void> {
  if (timer) clearTimeout(timer)
  timer = null
  try {
    job.value = await api.composeJob(props.jobId)
  } catch {
    // 轮询失败不打扰用户,下一轮再试。
  }
  if (running.value) timer = setTimeout(() => { void poll() }, 2000)
}

watch(() => props.jobId, () => {
  job.value = null
  void poll()
}, { immediate: true })
onBeforeUnmount(() => { if (timer) clearTimeout(timer) })
</script>

<template>
  <div class="space-y-2 text-sm">
    <div v-if="running" class="flex items-center gap-2">
      <Loader2 class="h-4 w-4 animate-spin text-primary" />
      {{ t(`structure.compose.stages.${job?.progress.stage ?? 'queued'}`) }}
    </div>
    <template v-else-if="job?.status === 'succeeded'">
      <div class="flex items-center gap-2 text-emerald-700 dark:text-emerald-300">
        <CircleCheck class="h-4 w-4" /> {{ t('structure.variant.succeeded') }}
      </div>
      <Button v-if="job.progress.question_id" size="sm" as-child>
        <NuxtLink :to="`/questions?id=${job.progress.question_id}`" @click="emit('open')">
          {{ t('structure.variant.open', { id: job.progress.question_id }) }}
        </NuxtLink>
      </Button>
    </template>
    <div v-else class="flex items-start gap-2 text-destructive">
      <TriangleAlert class="mt-0.5 h-4 w-4 shrink-0" />
      <span>{{ failure || t('structure.compose.failed') }}</span>
    </div>
  </div>
</template>
