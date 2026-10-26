<script setup lang="ts">
import { computed, onActivated, ref, watch } from 'vue'
import { AlertCircle, ChevronLeft, ChevronRight, Loader2, Plus, RotateCw } from '@lucide/vue'
import { toast } from 'vue-sonner'
import PageHeader from '@/components/PageHeader.vue'
import StimulusRow from '@/components/stimuli/StimulusRow.vue'
import ClearableInput from '@/components/ClearableInput.vue'
import ClearableSelect from '@/components/ClearableSelect.vue'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { buildLibraryQuery } from '@/lib/libraryQueries'
import { getApiErrorDetail, isRevisionConflict } from '@/lib/apiErrors'
import CompositionTargetPicker from '@/components/CompositionTargetPicker.vue'
import type { StimulusListItem, StimulusPage } from '@/types'

const { t } = useI18n()
const { currentSubjectId } = useSubjectContext()
const { can } = usePermissions()
const canEdit = computed(() => can(Capability.EDIT_QUESTION, currentSubjectId.value))
const { deleteStimulus, restoreStimulus, getStimulus } = useStimuli()

const pickerOpen = ref(false)
const pickerQuestionIds = ref<number[]>([])
const addToComposition = async (stimulus: StimulusListItem) => {
  if (!currentSubjectId.value) return
  try {
    const detail = await getStimulus(currentSubjectId.value, stimulus.id)
    pickerQuestionIds.value = detail.questions.map(question => question.id)
    pickerOpen.value = pickerQuestionIds.value.length > 0
  } catch (error) {
    toast.error(getApiErrorDetail(error, t('materials.detailLoadFailed')))
  }
}

const page = ref(1)
const size = ref(10)
const keyword = ref('')
const statusFilter = ref('0')
const visibility = ref('0')
const usage = ref('0')
const view = ref<'active' | 'deleted'>('active')
const query = computed(() => buildLibraryQuery({
  page: page.value,
  size: size.value,
  keyword: keyword.value.trim(),
  status: statusFilter.value,
  visibility: visibility.value,
  has_questions: usage.value === 'empty' ? false : usage.value === 'filled' ? true : undefined,
  only_deleted: view.value === 'deleted' ? true : undefined,
}))

const endpoint = computed(() => `/subjects/${currentSubjectId.value ?? 0}/stimuli`)
const { data, refresh, status, error } = await useAPI<StimulusPage>(endpoint, {
  query,
  immediate: false,
  watch: false,
})
const stimuli = computed(() => data.value?.items ?? [])
const total = computed(() => data.value?.total ?? 0)
const pages = computed(() => data.value?.pages ?? 0)

const load = () => currentSubjectId.value ? refresh() : Promise.resolve()
let hasActivated = false
onActivated(() => {
  if (hasActivated) load()
  hasActivated = true
})
watch(currentSubjectId, () => {
  page.value = 1
  load()
}, { immediate: true })
watch([page, size, keyword, statusFilter, visibility, usage, view], () => {
  if (page.value > 1 && (keyword.value || statusFilter.value !== '0' || visibility.value !== '0' || usage.value !== '0')) return
  load()
})
watch([keyword, statusFilter, visibility, usage, size, view], () => {
  if (page.value !== 1) page.value = 1
})

const statusOptions = computed(() => [
  { label: t('questions.filters.allStatuses'), value: '0' },
  { label: t('questions.statuses.draft'), value: 'draft' },
  { label: t('questions.statuses.pending'), value: 'pending' },
  { label: t('questions.statuses.published'), value: 'published' },
  { label: t('questions.statuses.archived'), value: 'archived' },
])
const visibilityOptions = computed(() => [
  { label: t('materials.filters.allVisibility'), value: '0' },
  { label: t('materials.filters.public'), value: 'public' },
  { label: t('materials.filters.private'), value: 'private' },
])
const usageOptions = computed(() => [
  { label: t('common.all'), value: '0' },
  { label: t('materials.filters.usageEmpty'), value: 'empty' },
  { label: t('materials.filters.usageFilled'), value: 'filled' },
])

const deleteItem = async (stimulus: StimulusListItem) => {
  if (!currentSubjectId.value || !confirm(t('materials.deleteConfirm', { id: stimulus.id }))) return
  try {
    await deleteStimulus(currentSubjectId.value, stimulus.id, stimulus.revision)
    toast.success(t('materials.movedToTrash'))
    if (stimuli.value.length === 1 && page.value > 1) page.value--
    else await refresh()
  } catch (error) {
    if (isRevisionConflict(error)) await refresh()
    toast.error(getApiErrorDetail(error, t('materials.deleteFailed')))
  }
}

const restoreItem = async (stimulus: StimulusListItem) => {
  if (!currentSubjectId.value) return
  try {
    await restoreStimulus(currentSubjectId.value, stimulus.id, stimulus.revision)
    toast.success(t('materials.restored'))
    if (stimuli.value.length === 1 && page.value > 1) page.value--
    else await refresh()
  } catch (error) {
    if (isRevisionConflict(error)) await refresh()
    toast.error(getApiErrorDetail(error, t('materials.restoreFailed')))
  }
}
</script>

<template>
  <PageHeader :title="t('nav.questionBank')">
    <template #actions>
      <Button v-if="canEdit" as-child size="sm">
        <NuxtLink to="/materials/new"><Plus class="mr-2 size-4" />{{ t('materials.create') }}</NuxtLink>
      </Button>
    </template>
  </PageHeader>
  <QuestionBankNav />

  <main class="flex flex-1 flex-col gap-5 px-4 py-6">
    <p class="text-sm text-muted-foreground">{{ t('materials.description') }}</p>
    <Tabs v-model="view">
      <TabsList><TabsTrigger value="active">{{ t('materials.tabs.active') }}</TabsTrigger><TabsTrigger value="deleted">{{ t('materials.tabs.deleted') }}</TabsTrigger></TabsList>
    </Tabs>
    <div class="grid gap-3 bg-muted/40 p-4 sm:grid-cols-4">
      <div class="space-y-2">
        <Label class="text-xs">{{ t('materials.filters.keyword') }}</Label>
        <ClearableInput v-model="keyword" :placeholder="t('materials.filters.keywordPlaceholder')" />
      </div>
      <div class="space-y-2">
        <Label class="text-xs">{{ t('materials.filters.status') }}</Label>
        <ClearableSelect v-model="statusFilter" :options="statusOptions" />
      </div>
      <div class="space-y-2">
        <Label class="text-xs">{{ t('materials.filters.visibility') }}</Label>
        <ClearableSelect v-model="visibility" :options="visibilityOptions" />
      </div>
      <div class="space-y-2">
        <Label class="text-xs">{{ t('materials.filters.usage') }}</Label>
        <ClearableSelect v-model="usage" :options="usageOptions" />
      </div>
    </div>

    <div v-if="!currentSubjectId" class="py-16 text-center text-sm text-muted-foreground">{{ t('materials.selectSubjectFirst') }}</div>
    <div v-else-if="status === 'pending'" class="flex justify-center py-16"><Loader2 class="size-7 animate-spin text-muted-foreground" /></div>
    <div v-else-if="error" class="flex flex-col items-center gap-3 py-16 text-sm text-muted-foreground">
      <AlertCircle class="size-6" /><span>{{ t('materials.loadFailed') }}</span>
      <Button variant="outline" size="sm" @click="load"><RotateCw class="mr-2 size-4" />{{ t('common.retry') }}</Button>
    </div>
    <div v-else-if="stimuli.length === 0" class="py-16 text-center text-sm text-muted-foreground">{{ view === 'deleted' ? t('materials.emptyDeleted') : t('materials.empty') }}</div>
    <section v-else class="border-y">
      <StimulusRow v-for="stimulus in stimuli" :key="stimulus.id" :stimulus="stimulus" :can-edit="canEdit" @delete="deleteItem" @restore="restoreItem" @add-composition="addToComposition" />
    </section>

    <div v-if="total > 0" class="flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
      <span>{{ t('materials.total', { total }) }}</span>
      <div class="flex items-center gap-2">
        <Button variant="outline" size="icon" :disabled="page <= 1" :title="t('common.prevPage')" :aria-label="t('common.prevPage')" @click="page--"><ChevronLeft class="size-4" /></Button>
        <span>{{ t('materials.pageInfo', { page, pages }) }}</span>
        <Button variant="outline" size="icon" :disabled="page >= pages" :title="t('common.nextPage')" :aria-label="t('common.nextPage')" @click="page++"><ChevronRight class="size-4" /></Button>
      </div>
    </div>
  </main>
  <CompositionTargetPicker v-model:open="pickerOpen" :subject-id="currentSubjectId" :question-ids="pickerQuestionIds" />
</template>