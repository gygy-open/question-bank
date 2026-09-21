<script setup lang="ts">
import { computed, onActivated, ref, watch } from 'vue'
import { AlertCircle, ChevronLeft, ChevronRight, Loader2, Plus, RotateCw } from '@lucide/vue'
import PageHeader from '@/components/PageHeader.vue'
import MaterialListItem from '@/components/materials/MaterialListItem.vue'
import ClearableInput from '@/components/ClearableInput.vue'
import ClearableSelect from '@/components/ClearableSelect.vue'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { buildLibraryQuery } from '@/lib/libraryQueries'
import type { StimulusPage } from '@/types'

const { currentSubjectId } = useSubjectContext()
const { can } = usePermissions()
const canEdit = computed(() => can(Capability.EDIT_QUESTION, currentSubjectId.value))

const page = ref(1)
const size = ref(10)
const keyword = ref('')
const statusFilter = ref('0')
const visibility = ref('0')
const query = computed(() => buildLibraryQuery({
  page: page.value,
  size: size.value,
  keyword: keyword.value.trim(),
  status: statusFilter.value,
  visibility: visibility.value,
}))

const endpoint = computed(() => `/subjects/${currentSubjectId.value ?? 0}/stimuli`)
const { data, refresh, status, error } = await useAPI<StimulusPage>(endpoint, {
  query,
  immediate: false,
  watch: false,
})
const materials = computed(() => data.value?.items ?? [])
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
watch([page, size, keyword, statusFilter, visibility], () => {
  if (page.value > 1 && (keyword.value || statusFilter.value !== '0' || visibility.value !== '0')) return
  load()
})
watch([keyword, statusFilter, visibility, size], () => {
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
</script>

<template>
  <PageHeader title="题库">
    <template #actions>
      <Button v-if="canEdit" as-child size="sm">
        <NuxtLink to="/materials/new"><Plus class="mr-2 size-4" />创建题目材料</NuxtLink>
      </Button>
    </template>
  </PageHeader>
  <QuestionBankNav />

  <main class="flex flex-1 flex-col gap-5 px-4 py-6">
    <p class="text-sm text-muted-foreground">供一道或多道题共同引用的文章、图表或背景内容；本身不可作答，也不包含答案和题型。</p>
    <div class="grid gap-3 bg-muted/40 p-4 sm:grid-cols-3">
      <div class="space-y-2">
        <Label class="text-xs">关键词</Label>
        <ClearableInput v-model="keyword" placeholder="搜索题目材料内容或来源" />
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
      <AlertCircle class="size-6" /><span>题目材料加载失败</span>
      <Button variant="outline" size="sm" @click="load"><RotateCw class="mr-2 size-4" />重试</Button>
    </div>
    <div v-else-if="materials.length === 0" class="py-16 text-center text-sm text-muted-foreground">暂无题目材料。创建后可在多个题组中复用。</div>
    <section v-else class="border-y">
      <MaterialListItem v-for="material in materials" :key="material.id" :material="material" :can-edit="canEdit" />
    </section>

    <div v-if="total > 0" class="flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
      <span>共 {{ total }} 条题目材料</span>
      <div class="flex items-center gap-2">
        <Button variant="outline" size="icon" :disabled="page <= 1" title="上一页" aria-label="上一页" @click="page--"><ChevronLeft class="size-4" /></Button>
        <span>第 {{ page }} / {{ pages }} 页</span>
        <Button variant="outline" size="icon" :disabled="page >= pages" title="下一页" aria-label="下一页" @click="page++"><ChevronRight class="size-4" /></Button>
      </div>
    </div>
  </main>
</template>