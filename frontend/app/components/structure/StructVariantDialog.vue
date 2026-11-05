<script setup lang="ts">
/**
 * 「生成变式」对话框(规格 §12.3 N1)。
 *
 * - 列出拆解中可替换的参数:原值、取值范围;每个参数可以填新值,或勾选「AI 取值」
 *   (仅取值范围已确认的参数可用),不填则保持原值;
 * - 实时预览替换后的题干(按原文区间替换,与后端规则一致);
 * - 提交后轮询任务:成功时给出新题链接(新题是草稿,需在题库中审核),失败时显示原因。
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import { CircleCheck, Loader2, TriangleAlert } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import MathText from '@/components/structure/MathText.vue'
import { getApiErrorDetail } from '@/lib/apiErrors'
import { formatParamDomain, replaceSpans, spanInMath } from '@/lib/structure'
import type { StructRun, StructVariantJob } from '~/types'

const props = defineProps<{ run: StructRun | null, questionId: number }>()
const open = defineModel<boolean>('open', { default: false })

const { t } = useI18n()
const api = useStructure()

/** 每个参数的新值与是否交给 AI 取值。 */
const inputs = ref<Record<number, { value: string, auto: boolean }>>({})
const submitting = ref(false)
const job = ref<StructVariantJob | null>(null)
let timer: ReturnType<typeof setTimeout> | null = null

const params = computed(() => (props.run?.params ?? []).filter(p => p.replaceable && p.span))
const finished = computed(() => !!job.value && ['succeeded', 'failed', 'cancelled'].includes(job.value.status))
const running = computed(() => !!job.value && !finished.value)
const hasChange = computed(() => params.value.some((p) => {
  const input = inputs.value[p.id]
  return !!input && (input.auto || (input.value.trim() !== '' && input.value.trim() !== p.value))
}))

/** 预览:填了新值的参数按区间替换;AI 取值的参数显示为「?」。 */
const preview = computed(() => {
  const r = props.run
  if (!r) return ''
  const replacements = params.value.flatMap((p) => {
    const input = inputs.value[p.id]
    if (!input) return []
    if (input.auto) return [{ span: p.span!, value: '?' }]
    const value = input.value.trim().replace(/^\$(.*)\$$/, '$1')
    return value && value !== p.value ? [{ span: p.span!, value }] : []
  })
  return replaceSpans(r.stem_text, replacements)
})

const failureText = computed(() => {
  const j = job.value
  if (!j || j.status !== 'failed') return ''
  const code = j.progress.error_code
  const key = `structure.variant.errors.${code}`
  const reason = code ? t(key) : ''
  return [reason !== key ? reason : '', j.error ?? ''].filter(Boolean).join(t('structure.variant.reasonSeparator'))
})

// region 操作

async function submit(): Promise<void> {
  if (!props.run || submitting.value) return
  submitting.value = true
  try {
    const values: Array<{ param_id: number, value: string }> = []
    const auto: number[] = []
    for (const p of params.value) {
      const input = inputs.value[p.id]
      if (!input) continue
      if (input.auto) auto.push(p.id)
      else if (input.value.trim() && input.value.trim() !== p.value) values.push({ param_id: p.id, value: input.value.trim() })
    }
    await api.createVariant({ question_id: props.questionId, run_id: props.run.id, values, auto_param_ids: auto })
    await poll()
  } catch (e) {
    toast.error(t('structure.variant.failed'), { description: getApiErrorDetail(e, '') })
  } finally {
    submitting.value = false
  }
}

async function poll(): Promise<void> {
  if (timer) clearTimeout(timer)
  timer = null
  try {
    job.value = (await api.variantJob(props.questionId)).job
  } catch {
    // 轮询失败不打扰用户,下一轮再试。
  }
  if (open.value && running.value) timer = setTimeout(() => { void poll() }, 2000)
}

function reset(): void {
  inputs.value = Object.fromEntries(params.value.map(p => [p.id, { value: '', auto: false }]))
  job.value = null
}

// endregion

watch(open, (value) => {
  if (value) reset()
  else if (timer) clearTimeout(timer)
})
onBeforeUnmount(() => { if (timer) clearTimeout(timer) })
</script>

<template>
  <Dialog v-model:open="open">
    <DialogContent class="sm:max-w-2xl">
      <DialogHeader>
        <DialogTitle>{{ t('structure.variant.title') }}</DialogTitle>
        <DialogDescription>{{ t('structure.variant.description') }}</DialogDescription>
      </DialogHeader>

      <div v-if="!job" class="space-y-4">
        <table class="w-full text-sm">
          <thead class="text-xs text-muted-foreground">
            <tr class="border-b">
              <th class="py-1.5 text-left font-normal">{{ t('structure.params.name') }}</th>
              <th class="py-1.5 text-left font-normal">{{ t('structure.variant.current') }}</th>
              <th class="py-1.5 text-left font-normal">{{ t('structure.variant.newValue') }}</th>
              <th class="py-1.5 text-left font-normal">{{ t('structure.variant.auto') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in params" :key="p.id" class="border-b align-top">
              <td class="py-2 pr-2">
                <div>{{ p.name }}</div>
                <div v-if="p.domain" class="text-xs text-muted-foreground">{{ formatParamDomain(p.domain) }}</div>
              </td>
              <td class="py-2 pr-2"><MathText :text="spanInMath(run!.stem_text, p.span!) ? `$${p.value}$` : p.value" /></td>
              <td class="py-2 pr-2">
                <Input
                  v-if="inputs[p.id]"
                  v-model="inputs[p.id]!.value"
                  class="h-8 w-36"
                  :disabled="inputs[p.id]!.auto"
                  :placeholder="p.value"
                />
              </td>
              <td class="py-2">
                <label
                  v-if="inputs[p.id]"
                  class="flex items-center gap-1.5 text-xs"
                  :title="p.domain_confirmed ? '' : t('structure.variant.autoNeedsDomain')"
                >
                  <Checkbox
                    :model-value="inputs[p.id]!.auto"
                    :disabled="!p.domain_confirmed"
                    @update:model-value="inputs[p.id]!.auto = $event === true"
                  />
                  <span :class="!p.domain_confirmed && 'text-muted-foreground'">{{ t('structure.variant.autoShort') }}</span>
                </label>
              </td>
            </tr>
          </tbody>
        </table>
        <div>
          <div class="mb-1 text-xs text-muted-foreground">{{ t('structure.variant.preview') }}</div>
          <div class="rounded-md border bg-muted/30 px-3 py-2 text-sm leading-7 whitespace-pre-wrap"><MathText :text="preview" /></div>
        </div>
      </div>

      <div v-else class="space-y-3 text-sm">
        <div v-if="running" class="flex items-center gap-2">
          <Loader2 class="h-4 w-4 animate-spin text-primary" />
          {{ t(`structure.variant.stages.${job.progress.stage ?? 'queued'}`) }}
        </div>
        <div v-else-if="job.status === 'succeeded'" class="space-y-2">
          <div class="flex items-center gap-2 text-emerald-700 dark:text-emerald-300">
            <CircleCheck class="h-4 w-4" /> {{ t('structure.variant.succeeded') }}
          </div>
          <ul v-if="job.progress.changes" class="text-xs text-muted-foreground">
            <li v-for="(change, name) in job.progress.changes" :key="name">
              {{ t('structure.variant.change', { name, from: change[0], to: change[1] }) }}
            </li>
          </ul>
          <p v-if="job.progress.options_rewritten" class="text-xs text-amber-700 dark:text-amber-300">
            {{ t('structure.variant.optionsRewritten') }}
          </p>
          <Button v-if="job.progress.question_id" size="sm" as-child>
            <NuxtLink :to="`/questions?id=${job.progress.question_id}`" @click="open = false">
              {{ t('structure.variant.open', { id: job.progress.question_id }) }}
            </NuxtLink>
          </Button>
        </div>
        <div v-else class="flex items-start gap-2 text-destructive">
          <TriangleAlert class="mt-0.5 h-4 w-4 shrink-0" />
          <span>{{ failureText || t('structure.variant.failed') }}</span>
        </div>
      </div>

      <DialogFooter>
        <Button v-if="job && finished" variant="outline" @click="reset">{{ t('structure.variant.again') }}</Button>
        <Button v-if="!job" variant="outline" @click="open = false">{{ t('common.cancel') }}</Button>
        <Button v-if="!job" :disabled="submitting || !hasChange" @click="submit">
          <Loader2 v-if="submitting" class="mr-2 h-4 w-4 animate-spin" />
          {{ t('structure.variant.submit') }}
        </Button>
        <Button v-if="job && finished" @click="open = false">{{ t('common.close') }}</Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
