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
    toast.error(getApiErrorDetail(error, '加载材料题失败'))
  }
}

const page = ref(1)
const size = ref(10)
const keyword = ref('')
const statusFilter = ref('0')
const visibility = ref('0')
const view = ref<'active' | 'deleted'>('active')
const query = computed(() => buildLibraryQuery({
  page: page.value,
  size: size.value,
  keyword: keyword.value.trim(),
  status: statusFilter.value,
  visibility: visibility.value,
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
watch([page, size, keyword, statusFilter, visibility, view], () => {
  if (page.value > 1 && (keyword.value || statusFilter.value !== '0' || visibility.value !== '0')) return
  load()
})
watch([keyword, statusFilter, visibility, size, view], () => {
  if (page.value !== 1) page.value = 1
})

const statusOptions = [
  { label: '全部状态', value: '0' },
  { label: '草稿', value: 'draft' },
  { label: '待审核', value: 'pending' },
  { label: '已发布', value: 'published' },
  { label: '已归档', value: 'archived' },
]
const visibilityOptions = [
  { label: '全部可见性', value: '0' },
  { label: '公开', value: 'public' },
  { label: '私有', value: 'private' },
]

const deleteItem = async (stimulus: StimulusListItem) => {
  if (!currentSubjectId.value || !confirm(`确定删除材料题 #${stimulus.id} 吗？`)) return
  try {
    await deleteStimulus(currentSubjectId.value, stimulus.id, stimulus.revision)
    toast.success('材料题已移入回收站')
    if (stimuli.value.length === 1 && page.value > 1) page.value--
    else await refresh()
  } catch (error) {
    if (isRevisionConflict(error)) await refresh()
    toast.error(getApiErrorDetail(error, '删除材料题失败'))
  }
}

const restoreItem = async (stimulus: StimulusListItem) => {
  if (!currentSubjectId.value) return
  try {
    await restoreStimulus(currentSubjectId.value, stimulus.id, stimulus.revision)
    toast.success('材料题已恢复')
    if (stimuli.value.length === 1 && page.value > 1) page.value--
    else await refresh()
  } catch (error) {
    if (isRevisionConflict(error)) await refresh()
    toast.error(getApiErrorDetail(error, '恢复材料题失败'))
  }
}
</script>

<template>
  <PageHeader title="题库">
    <template #actions>
      <Button v-if="canEdit" as-child size="sm">
        <NuxtLink to="/materials/new"><Plus class="mr-2 size-4" />新建材料题</NuxtLink>
      </Button>
    </template>
  </PageHeader>
  <QuestionBankNav />

  <main class="flex flex-1 flex-col gap-5 px-4 py-6">
    <p class="text-sm text-muted-foreground">一段文章、图表或背景材料加上围绕它的若干小题，如阅读理解、完形填空、材料分析。加入稿件时材料与小题一起出现。</p>
    <Tabs v-model="view">
      <TabsList><TabsTrigger value="active">当前</TabsTrigger><TabsTrigger value="deleted">回收站</TabsTrigger></TabsList>
    </Tabs>
    <div class="grid gap-3 bg-muted/40 p-4 sm:grid-cols-3">
      <div class="space-y-2">
        <Label class="text-xs">关键词</Label>
        <ClearableInput v-model="keyword" placeholder="搜索材料内容或来源" />
      </div>
      <div class="space-y-2">
        <Label class="text-xs">状态</Label>
        <ClearableSelect v-model="statusFilter" :options="statusOptions" />
      </div>
      <div class="space-y-2">
        <Label class="text-xs">可见性</Label>
        <ClearableSelect v-model="visibility" :options="visibilityOptions" />
      </div>
    </div>

    <div v-if="!currentSubjectId" class="py-16 text-center text-sm text-muted-foreground">请先选择学科</div>
    <div v-else-if="status === 'pending'" class="flex justify-center py-16"><Loader2 class="size-7 animate-spin text-muted-foreground" /></div>
    <div v-else-if="error" class="flex flex-col items-center gap-3 py-16 text-sm text-muted-foreground">
      <AlertCircle class="size-6" /><span>材料题加载失败</span>
      <Button variant="outline" size="sm" @click="load"><RotateCw class="mr-2 size-4" />重试</Button>
    </div>
    <div v-else-if="stimuli.length === 0" class="py-16 text-center text-sm text-muted-foreground">{{ view === 'deleted' ? '回收站中暂无材料题。' : '暂无材料题。' }}</div>
    <section v-else class="border-y">
      <StimulusRow v-for="stimulus in stimuli" :key="stimulus.id" :stimulus="stimulus" :can-edit="canEdit" @delete="deleteItem" @restore="restoreItem" @add-composition="addToComposition" />
    </section>

    <div v-if="total > 0" class="flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
      <span>共 {{ total }} 道材料题</span>
      <div class="flex items-center gap-2">
        <Button variant="outline" size="icon" :disabled="page <= 1" title="上一页" aria-label="上一页" @click="page--"><ChevronLeft class="size-4" /></Button>
        <span>第 {{ page }} / {{ pages }} 页</span>
        <Button variant="outline" size="icon" :disabled="page >= pages" title="下一页" aria-label="下一页" @click="page++"><ChevronRight class="size-4" /></Button>
      </div>
    </div>
  </main>
  <CompositionTargetPicker v-model:open="pickerOpen" :subject-id="currentSubjectId" :question-ids="pickerQuestionIds" />
</template>