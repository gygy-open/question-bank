<script setup lang="ts">
import { ref, reactive, watch, onMounted } from 'vue'
import { toast } from 'vue-sonner'
import { Save, MessageSquareText, FileText, BrainCircuit, Wrench, RotateCcw, ClipboardCopy } from '@lucide/vue'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { Subject } from '~/types'
import { filterPromptManageableSubjects } from '@/lib/subjectPromptAccess'

const { t, te } = useI18n()
const { $api } = useNuxtApp()
const { permissions } = usePermissions()

interface SubjectPrompt {
  key: string
  title: string
  description: string
  default: string
  value: string | null
  is_custom: boolean
}

// 图标按 key 映射；标题/描述按 key 走前端翻译，未登记的 key 回退到后端返回值
const iconMap: Record<string, any> = {
  AI_EXTRACT_PROMPT: FileText,
  AI_SOLVE_PROMPT: BrainCircuit,
}

const promptTitle = (p: SubjectPrompt) =>
  te(`prompts.items.${p.key}.title`) ? t(`prompts.items.${p.key}.title`) : p.title
const promptDescription = (p: SubjectPrompt) =>
  te(`prompts.items.${p.key}.description`) ? t(`prompts.items.${p.key}.description`) : p.description

const availableSubjects = ref<Subject[]>([])
const subjects = computed(() =>
  filterPromptManageableSubjects(availableSubjects.value, permissions.value),
)
const selectedSubjectId = ref<string>('')
const prompts = ref<SubjectPrompt[]>([])
const drafts = reactive<Record<string, string>>({})
const loading = ref(false)
const saving = reactive<Record<string, boolean>>({})

const fetchSubjects = async () => {
  try {
    availableSubjects.value = await $api<Subject[]>('/subjects')
    if (subjects.value.length && !selectedSubjectId.value) {
      selectedSubjectId.value = String(subjects.value[0].id)
    }
  } catch (error) {
    toast.error(t('prompts.toast.fetchSubjectsFailed'), { description: (error as any).message })
  }
}

const fetchPrompts = async () => {
  if (!selectedSubjectId.value) {
    prompts.value = []
    return
  }
  loading.value = true
  try {
    const data = await $api<SubjectPrompt[]>(`/subjects/${selectedSubjectId.value}/prompts`)
    prompts.value = data
    for (const p of data) drafts[p.key] = p.value ?? ''
  } catch (error) {
    toast.error(t('prompts.toast.fetchFailed'), { description: (error as any).message })
  } finally {
    loading.value = false
  }
}

const fillWithDefault = (p: SubjectPrompt) => {
  drafts[p.key] = p.default
}

const save = async (p: SubjectPrompt) => {
  const value = (drafts[p.key] ?? '').trim()
  if (!value) {
    toast.error(t('prompts.toast.empty'), { description: t('prompts.toast.emptyDescription') })
    return
  }
  saving[p.key] = true
  try {
    await $api(`/subjects/${selectedSubjectId.value}/prompts/${p.key}`, {
      method: 'PUT',
      body: { value: drafts[p.key] },
    })
    toast.success(t('common.saved'), { description: t('prompts.toast.savedDescription', { title: promptTitle(p) }) })
    await fetchPrompts()
  } catch (error) {
    toast.error(t('common.saveFailed'), { description: (error as any).message })
  } finally {
    saving[p.key] = false
  }
}

const reset = async (p: SubjectPrompt) => {
  saving[p.key] = true
  try {
    await $api(`/subjects/${selectedSubjectId.value}/prompts/${p.key}`, { method: 'DELETE' })
    toast.success(t('prompts.toast.resetDone'), { description: t('prompts.toast.resetDescription', { title: promptTitle(p) }) })
    await fetchPrompts()
  } catch (error) {
    toast.error(t('prompts.toast.resetFailed'), { description: (error as any).message })
  } finally {
    saving[p.key] = false
  }
}

watch(selectedSubjectId, fetchPrompts)
watch(subjects, (manageable) => {
  if (manageable.some(subject => String(subject.id) === selectedSubjectId.value)) return
  selectedSubjectId.value = manageable.length ? String(manageable[0].id) : ''
})

onMounted(async () => {
  await fetchSubjects()
  await fetchPrompts()
})
</script>


<template>
  <div class="space-y-6">
    <!-- 学科选择 -->
    <div v-if="subjects.length" class="flex items-center gap-3 max-w-4xl">
      <span class="text-sm font-medium shrink-0">{{ t('prompts.subject') }}</span>
      <Select v-model="selectedSubjectId">
        <SelectTrigger class="w-64">
          <SelectValue :placeholder="t('prompts.selectSubject')" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem v-for="s in subjects" :key="s.id" :value="String(s.id)">
            {{ s.name }}
          </SelectItem>
        </SelectContent>
      </Select>
      <p class="text-xs text-muted-foreground">
        {{ t('prompts.subjectHint') }}
      </p>
    </div>

    <div v-if="loading" class="flex justify-center py-8">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
    </div>

    <div v-else-if="subjects.length" class="max-w-4xl">
      <Accordion type="single" collapsible class="w-full space-y-4">
        <AccordionItem
          v-for="p in prompts"
          :key="p.key"
          :value="p.key"
          class="border rounded-xl bg-card px-4"
        >
          <AccordionTrigger class="hover:no-underline py-4">
            <div class="flex items-center gap-4 text-left">
              <div class="p-2.5 bg-primary/10 rounded-lg text-primary shrink-0">
                <component :is="iconMap[p.key] || Wrench" class="w-5 h-5" />
              </div>
              <div>
                <div class="flex items-center gap-2">
                  <h3 class="font-semibold text-base">{{ promptTitle(p) }}</h3>
                  <Badge variant="outline" class="text-[10px] font-mono py-0 h-4">{{ p.key }}</Badge>
                  <Badge
                    :variant="p.is_custom ? 'default' : 'secondary'"
                    class="text-[10px] py-0 h-4"
                  >
                    {{ p.is_custom ? t('prompts.custom') : t('prompts.usingDefault') }}
                  </Badge>
                </div>
                <p class="text-xs text-muted-foreground mt-0.5 line-clamp-1 font-normal">
                  {{ promptDescription(p) }}
                </p>
              </div>
            </div>
          </AccordionTrigger>
          <AccordionContent class="pt-2 pb-6">
            <div class="flex flex-col gap-3 pl-[3.25rem]">
              <Textarea
                v-model="drafts[p.key]"
                :placeholder="t('prompts.placeholder')"
                class="min-h-[300px] font-mono text-[13px] leading-relaxed resize-y bg-muted/30 focus:bg-background"
              />

              <details class="text-xs">
                <summary class="cursor-pointer text-muted-foreground hover:text-foreground select-none">
                  {{ t('prompts.viewDefault') }}
                </summary>
                <pre class="mt-2 p-3 rounded-lg bg-muted/50 whitespace-pre-wrap font-mono text-[12px] leading-relaxed max-h-64 overflow-auto">{{ p.default }}</pre>
              </details>

              <div class="flex items-center justify-between gap-2 mt-1">
                <p class="text-xs text-muted-foreground flex-1">
                  <i18n-t scope="global" keypath="prompts.placeholdersHint" tag="span">
                    <template #name><code>{subject_name}</code></template>
                    <template #description><code>{subject_description}</code></template>
                  </i18n-t>
                </p>
                <div class="flex items-center gap-2 shrink-0">
                  <Button variant="ghost" size="sm" @click="fillWithDefault(p)">
                    <ClipboardCopy class="w-4 h-4 mr-1.5" />
                    {{ t('prompts.fillDefault') }}
                  </Button>
                  <Button
                    v-if="p.is_custom"
                    variant="outline"
                    size="sm"
                    :disabled="saving[p.key]"
                    @click="reset(p)"
                  >
                    <RotateCcw class="w-4 h-4 mr-1.5" />
                    {{ t('prompts.resetToDefault') }}
                  </Button>
                  <Button size="sm" :disabled="saving[p.key]" @click="save(p)">
                    <Save class="w-4 h-4 mr-1.5" />
                    {{ t('prompts.saveOverride') }}
                  </Button>
                </div>
              </div>
            </div>
          </AccordionContent>
        </AccordionItem>
      </Accordion>

      <div v-if="!loading && prompts.length === 0" class="flex flex-col items-center justify-center p-12 text-center border rounded-xl bg-card border-dashed">
        <MessageSquareText class="w-8 h-8 text-muted-foreground/50 mb-4" />
        <h3 class="text-lg font-medium">{{ t('prompts.emptyTitle') }}</h3>
        <p class="text-sm text-muted-foreground mt-1">{{ t('prompts.emptyDescription') }}</p>
      </div>
    </div>

    <div v-else class="flex max-w-4xl flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
      <MessageSquareText class="mb-4 h-8 w-8 text-muted-foreground/50" />
      <h3 class="text-lg font-medium">{{ t('prompts.noSubjectsTitle') }}</h3>
      <p class="mt-1 text-sm text-muted-foreground">{{ t('prompts.noSubjectsDescription') }}</p>
    </div>
  </div>
</template>
