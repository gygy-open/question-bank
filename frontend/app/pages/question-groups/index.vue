<script setup lang="ts">
import { computed, onActivated, ref, watch } from 'vue'
import { AlertCircle, ChevronLeft, ChevronRight, Loader2, Plus, RotateCw } from '@lucide/vue'
import { toast } from 'vue-sonner'
import PageHeader from '@/components/PageHeader.vue'
import QuestionGroupListItem from '@/components/question-groups/QuestionGroupListItem.vue'
import CompositionTargetPicker from '@/components/CompositionTargetPicker.vue'
import ClearableInput from '@/components/ClearableInput.vue'
import ClearableSelect from '@/components/ClearableSelect.vue'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { buildLibraryQuery } from '@/lib/libraryQueries'
import { isRevisionConflict } from '@/lib/questionGroupEditor'
import { richDocToPlainText } from '@/components/rich-editor/richDoc'
import type { QuestionGroup, QuestionGroupPage } from '@/types'

const route = useRoute()
const router = useRouter()
const { $api } = useNuxtApp()
const { currentSubjectId } = useSubjectContext()
const { can } = usePermissions()
const basket = useQuestionBasket()
const canEdit = computed(() => can(Capability.EDIT_QUESTION, currentSubjectId.value))

const page = ref(1)
const size = ref(10)
const keyword = ref('')
const statusFilter = ref('0')
const visibility = ref('0')
const stimulusId = ref('')
const questionId = ref(typeof route.query.question_id === 'string' ? route.query.question_id : '')
const query = computed(() => buildLibraryQuery({
  page: page.value, size: size.value, keyword: keyword.value.trim(), status: statusFilter.value,
  visibility: visibility.value, stimulus_id: stimulusId.value, question_id: questionId.value,
}))

const endpoint = computed(() => `/subjects/${currentSubjectId.value ?? 0}/question-groups`)
const { data, refresh, status, error } = await useAPI<QuestionGroupPage>(endpoint, {
  query, immediate: false, watch: false,
})
const groups = computed(() => data.value?.items ?? [])
const total = computed(() => data.value?.total ?? 0)
const pages = computed(() => data.value?.pages ?? 0)
const load = () => currentSubjectId.value ? refresh() : Promise.resolve()

let hasActivated = false
onActivated(() => {
  questionId.value = typeof route.query.question_id === 'string' ? route.query.question_id : ''
  if (hasActivated) load()
  hasActivated = true
})
watch(() => route.query.question_id, value => {
  questionId.value = typeof value === 'string' ? value : ''
  page.value = 1
})
watch(currentSubjectId, () => { page.value = 1; load() }, { immediate: true })
watch([page, size, keyword, statusFilter, visibility, stimulusId, questionId], load)
watch([size, keyword, statusFilter, visibility, stimulusId, questionId], () => {
  if (page.value !== 1) page.value = 1
})

const statusOptions = [
  { label: '全部状态', value: '0' }, { label: '草稿', value: 'draft' },
  { label: '待审核', value: 'pending' }, { label: '已发布', value: 'published' },
  { label: '已归档', value: 'archived' },
]
const visibilityOptions = [
  { label: '全部可见性', value: '0' }, { label: '公开', value: 'public' }, { label: '私有', value: 'private' },
]

const deleteGroup = async (group: QuestionGroup) => {
  if (!currentSubjectId.value || !confirm(`确定删除题组 #${group.id} 吗？题目材料和题目不会被删除。`)) return
  try {
    await $api(`/subjects/${currentSubjectId.value}/question-groups/${group.id}`, {
      method: 'DELETE', query: { expected_revision: group.revision },
    })
    toast.success('题组已删除')
    if (groups.value.length === 1 && page.value > 1) page.value--
    else await refresh()
  } catch (error) {
    if (isRevisionConflict(error)) {
      await refresh()
      toast.error('题组已被其他人修改，列表已刷新，请确认后重试')
    } else {
      toast.error('删除题组失败，请刷新后重试')
    }
  }
}

const addToBasket = (group: QuestionGroup) => {
  basket.addMany(group.items.map(({ question }) => ({
    id: question.id, subject_id: group.subject_id,
    content_preview: richDocToPlainText(question.content).slice(0, 40),
    q_type: question.q_type, difficulty: question.difficulty,
  })))
  toast.success(`已将 ${group.items.length} 道题加入试题篮`)
}

const pickerOpen = ref(false)
const pickerQuestionGroupId = ref<number>()
const addToComposition = (group: QuestionGroup) => {
  pickerQuestionGroupId.value = group.id
  pickerOpen.value = true
}

const clearQuestionFilter = () => {
  questionId.value = ''
  router.replace({ query: { ...route.query, question_id: undefined } })
}
</script>

<template>
  <PageHeader title="题库">
    <template #actions>
      <Button v-if="canEdit" as-child size="sm"><NuxtLink to="/question-groups/new"><Plus class="mr-2 size-4" />创建题组</NuxtLink></Button>
    </template>
  </PageHeader>
  <QuestionBankNav />

  <main class="flex flex-1 flex-col gap-5 px-4 py-6">
    <p class="text-sm text-muted-foreground">由一份题目材料和若干有序题目组成；题号、分值和试卷版面由具体稿件管理。</p>
    <div class="grid gap-3 bg-muted/40 p-4 sm:grid-cols-2 xl:grid-cols-5">
      <div class="space-y-2 xl:col-span-2"><Label class="text-xs">关键词</Label><ClearableInput v-model="keyword" placeholder="搜索题目材料、题目或来源" /></div>
      <div class="space-y-2"><Label class="text-xs">状态</Label><ClearableSelect v-model="statusFilter" :options="statusOptions" /></div>
      <div class="space-y-2"><Label class="text-xs">可见性</Label><ClearableSelect v-model="visibility" :options="visibilityOptions" /></div>
      <div class="space-y-2"><Label class="text-xs">题目材料 ID</Label><ClearableInput v-model="stimulusId" type="number" placeholder="精确筛选" /></div>
      <div v-if="questionId" class="flex items-center gap-2 text-sm text-muted-foreground sm:col-span-2 xl:col-span-5">
        正在显示包含题目 #{{ questionId }} 的题组
        <Button variant="link" size="sm" class="h-auto p-0" @click="clearQuestionFilter">清除</Button>
      </div>
    </div>

    <div v-if="!currentSubjectId" class="py-16 text-center text-sm text-muted-foreground">请先选择学科</div>
    <div v-else-if="status === 'pending'" class="flex justify-center py-16"><Loader2 class="size-7 animate-spin text-muted-foreground" /></div>
    <div v-else-if="error" class="flex flex-col items-center gap-3 py-16 text-sm text-muted-foreground">
      <AlertCircle class="size-6" /><span>题组加载失败</span><Button variant="outline" size="sm" @click="load"><RotateCw class="mr-2 size-4" />重试</Button>
    </div>
    <div v-else-if="groups.length === 0" class="py-16 text-center text-sm text-muted-foreground">暂无题组。创建后可选择题目材料并添加、排序题目。</div>
    <section v-else class="border-y">
      <QuestionGroupListItem v-for="group in groups" :key="group.id" :group="group" :can-edit="canEdit" @delete="deleteGroup" @add-basket="addToBasket" @add-composition="addToComposition" />
    </section>

    <div v-if="total > 0" class="flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
      <span>共 {{ total }} 个题组</span>
      <div class="flex items-center gap-2">
        <Button variant="outline" size="icon" :disabled="page <= 1" title="上一页" aria-label="上一页" @click="page--"><ChevronLeft class="size-4" /></Button>
        <span>第 {{ page }} / {{ pages }} 页</span>
        <Button variant="outline" size="icon" :disabled="page >= pages" title="下一页" aria-label="下一页" @click="page++"><ChevronRight class="size-4" /></Button>
      </div>
    </div>
  </main>

  <CompositionTargetPicker v-model:open="pickerOpen" :subject-id="currentSubjectId" :question-group-id="pickerQuestionGroupId" />
</template>