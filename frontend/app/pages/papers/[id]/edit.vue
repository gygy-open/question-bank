<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import draggable from 'vuedraggable'
import { useDebounceFn } from '@vueuse/core'
import { Button } from '@/components/ui/button'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Separator } from '@/components/ui/separator'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import { Checkbox } from '@/components/ui/checkbox'
import {
  ArrowLeft, Download, Loader2, CheckCircle, Plus, FileDown, Trash2, Heading2,
} from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import PaperQuestionCard from '@/components/PaperQuestionCard.vue'
import PaperQuestionDetailSheet from '@/components/PaperQuestionDetailSheet.vue'
import { usePapers } from '~/composables/usePapers'
import type { PaperDetail, PaperItem, Subject, KnowledgePoint } from '~/types'

const route = useRoute()
const router = useRouter()
const paperId = Number(route.params.id)

const { get, update, removeItem, reorder, download, updateItem } = usePapers()
const { data: subjects } = await useAPI<Subject[]>('/subjects')
const { data: knowledgePoints } = await useAPI<KnowledgePoint[]>('/knowledge-points', {
  query: { limit: -1 },
})

const paper = ref<PaperDetail | null>(null)
const items = ref<PaperItem[]>([])
const loading = ref(true)

type Block =
  | { kind: 'section'; id: string; title: string; ownerId: number }
  | { kind: 'question'; id: number; item: PaperItem }

const blocks = ref<Block[]>([])

const rebuildBlocks = () => {
  const arr: Block[] = []
  for (const it of items.value) {
    if (it.section_title) {
      arr.push({ kind: 'section', id: `sec-${it.id}`, title: it.section_title, ownerId: it.id })
    }
    arr.push({ kind: 'question', id: it.id, item: it })
  }
  blocks.value = arr
}

const saving = ref(false)
const saved = ref(false)
const savingStatus = ref('')

const detailSheetOpen = ref(false)
const detailQuestionId = ref<number | null>(null)

const load = async () => {
  loading.value = true
  try {
    const data = await get(paperId)
    paper.value = data
    items.value = [...data.items]
    rebuildBlocks()
  } catch {
    toast.error('加载试卷失败')
    router.push('/papers')
  } finally {
    loading.value = false
  }
}

await load()

const stats = computed(() => {
  const byType: Record<string, number> = {}
  const byDifficulty: Record<number, number> = {}
  for (const it of items.value) {
    if (!it.question) continue
    byType[it.question.q_type] = (byType[it.question.q_type] || 0) + 1
    byDifficulty[it.question.difficulty] = (byDifficulty[it.question.difficulty] || 0) + 1
  }
  return { byType, byDifficulty }
})

const typeStatList = computed(() => {
  const labels: Record<string, string> = {
    single_choice: '单选题', multiple_choice: '多选题', true_false: '判断题',
    fill_in_the_blank: '填空题', free_response: '解答题',
  }
  return Object.entries(stats.value.byType).map(([k, v]) => ({
    label: labels[k] || k, count: v,
  }))
})
const displayNumbers = computed<Record<number, number>>(() => {
  const map: Record<number, number> = {}
  let counter = 0
  for (const b of blocks.value) {
    if (b.kind === 'section') {
      counter = 0
      continue
    }
    counter += 1
    map[b.id] = counter
  }
  return map
})

const insertSectionOpen = ref(false)
const insertTargetId = ref<number | null>(null)
const newSectionTitle = ref('')

const openInsertSection = (item: PaperItem | undefined | null) => {
  if (!item) {
    toast.error('请先添加题目')
    return
  }
  insertTargetId.value = item.id
  newSectionTitle.value = item.section_title || ''
  insertSectionOpen.value = true
}

const doInsertSection = async () => {
  const title = newSectionTitle.value.trim()
  if (!title || insertTargetId.value == null) return
  const targetItem = items.value.find((i) => i.id === insertTargetId.value)
  if (!targetItem) return
  try {
    await updateItem(paperId, targetItem.id, { section_title: title })
    targetItem.section_title = title
    rebuildBlocks()
    insertSectionOpen.value = false
    toast.success('大题已添加')
  } catch {
    toast.error('添加大题失败')
  }
}

const editingSectionId = ref<number | null>(null)
const editSectionDraft = ref('')

const startEditSection = (ownerId: number, current: string) => {
  editSectionDraft.value = current
  editingSectionId.value = ownerId
}

const commitEditSection = async () => {
  const ownerId = editingSectionId.value
  editingSectionId.value = null
  if (ownerId == null) return
  const item = items.value.find((i) => i.id === ownerId)
  if (!item) return
  const title = editSectionDraft.value.trim()
  if (title === (item.section_title || '')) return
  try {
    await updateItem(paperId, ownerId, { section_title: title || null })
    item.section_title = title || null
    rebuildBlocks()
    if (!title) toast.success('大题已删除')
  } catch {
    toast.error('保存失败')
  }
}

const removeSection = async (ownerId: number) => {
  const item = items.value.find((i) => i.id === ownerId)
  if (!item) return
  try {
    await updateItem(paperId, ownerId, { section_title: null })
    item.section_title = null
    rebuildBlocks()
    editingSectionId.value = null
    toast.success('大题已删除')
  } catch {
    toast.error('删除失败')
  }
}

const savePaperInfo = useDebounceFn(async () => {
  if (!paper.value) return
  saving.value = true
  savingStatus.value = '保存中...'
  try {
    await update(paperId, {
      title: paper.value.title,
      subject_id: paper.value.subject_id ?? null,
      description: paper.value.description ?? null,
    })
    saved.value = true
    savingStatus.value = '已保存'
    setTimeout(() => { saved.value = false }, 3000)
  } catch {
    savingStatus.value = '保存失败'
  } finally {
    saving.value = false
  }
}, 1500)

const onDragEnd = async () => {
  if (!paper.value) return
  // 记录旧标题以计算差异
  const oldTitles = new Map(items.value.map((i) => [i.id, i.section_title ?? null]))

  // 从 blocks 顺序重建题目列表与分节归属：标题块归属其后的第一道题
  const newItems: PaperItem[] = []
  let pendingTitle: string | null = null
  for (const b of blocks.value) {
    if (b.kind === 'section') {
      pendingTitle = b.title
      continue
    }
    b.item.section_title = pendingTitle
    pendingTitle = null
    newItems.push(b.item)
  }
  items.value = newItems

  saving.value = true
  savingStatus.value = '保存中...'
  try {
    for (const it of newItems) {
      const old = oldTitles.get(it.id) ?? null
      const cur = it.section_title ?? null
      if (old !== cur) {
        await updateItem(paperId, it.id, { section_title: cur })
      }
    }
    await reorder(paperId, newItems.map((i) => i.id))
    saved.value = true
    savingStatus.value = '已保存'
    setTimeout(() => { saved.value = false }, 3000)
  } catch {
    savingStatus.value = '排序保存失败'
    await load()
    return
  } finally {
    saving.value = false
  }
  rebuildBlocks()
}

const onRemoveItem = async (item: PaperItem) => {
  const prev = [...items.value]
  items.value = items.value.filter((i) => i.id !== item.id)
  rebuildBlocks()
  try {
    await removeItem(paperId, item.id)
    if (paper.value) paper.value.question_count = items.value.length
  } catch {
    toast.error('移除失败')
    items.value = prev
    rebuildBlocks()
  }
}

const viewQuestion = (item: PaperItem) => {
  if (item.question) {
    detailQuestionId.value = item.question.id
    detailSheetOpen.value = true
  }
}

const goToLibrary = () => {
  router.push('/questions')
}

// --- Export ---
const exportOpen = ref(false)
const exporting = ref(false)
const exportForm = ref({
  format: 'docx' as 'docx' | 'latex',
  include_answer: false,
  include_analysis: false,
  include_explanation: false,
  include_summary: false,
  include_source: false,
})

const doExport = async () => {
  if (!paper.value) return
  exporting.value = true
  try {
    const blob = await download(paperId, {
      title: paper.value.title,
      ...exportForm.value,
    })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    const ext = exportForm.value.format === 'latex' ? 'zip' : exportForm.value.format
    link.setAttribute('download', `${paper.value.title}.${ext}`)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
    exportOpen.value = false
    toast.success('试卷已导出')
  } catch {
    toast.error('导出失败')
  } finally {
    exporting.value = false
  }
}

watch(
  () => paper.value?.title,
  (v, old) => { if (old !== undefined && v !== old) savePaperInfo() }
)
</script>

<template>
  <div v-if="loading" class="flex-1 flex items-center justify-center">
    <Loader2 class="h-8 w-8 animate-spin text-muted-foreground" />
  </div>

  <div v-else-if="paper" class="flex flex-col h-[calc(100vh-0px)]">
    <!-- Top toolbar -->
    <div class="border-b bg-background sticky top-0 z-10">
      <div class="flex items-center justify-between px-4 py-3 gap-3">
        <div class="flex items-center gap-3 min-w-0">
          <Button variant="ghost" size="icon" @click="router.push('/papers')">
            <ArrowLeft class="h-4 w-4" />
          </Button>
          <div class="min-w-0">
            <h1 class="text-lg font-semibold truncate">{{ paper.title }}</h1>
            <p class="text-sm text-muted-foreground">{{ items.length }} 题</p>
          </div>
        </div>

        <div class="flex items-center gap-2">
          <div class="text-sm text-muted-foreground flex items-center gap-1.5 min-w-[80px]">
            <Loader2 v-if="saving" class="h-3 w-3 animate-spin" />
            <CheckCircle v-else-if="saved" class="h-3 w-3 text-green-600" />
            <span>{{ savingStatus }}</span>
          </div>
          <Separator orientation="vertical" class="h-6" />
          <Button size="sm" @click="exportOpen = true">
            <Download class="mr-2 h-4 w-4" /> 导出
          </Button>
        </div>
      </div>
    </div>

    <!-- Main -->
    <div class="flex flex-1 overflow-hidden">
      <!-- Left: paper preview -->
      <div class="flex-1 overflow-y-auto bg-muted/30">
        <div class="p-6 max-w-3xl mx-auto">
          <div class="flex items-center justify-between mb-4">
            <div class="text-sm text-muted-foreground">共 {{ items.length }} 道题目</div>
            <Button variant="outline" size="sm" @click="goToLibrary">
              <Plus class="mr-2 h-4 w-4" /> 去题库添加
            </Button>
          </div>

          <!-- 纸张 -->
          <div
            v-if="items.length > 0"
            class="bg-background rounded-lg shadow-sm border px-10 py-8"
          >
            <!-- 试卷抬头 -->
            <div class="text-center mb-6 pb-4 border-b">
              <h1 class="text-2xl font-bold">{{ paper.title }}</h1>
              <p v-if="paper.description" class="text-sm text-muted-foreground mt-2">
                {{ paper.description }}
              </p>
            </div>

            <draggable
              v-model="blocks"
              item-key="id"
              handle=".drag-handle"
              :animation="200"
              @end="onDragEnd"
            >
              <template #item="{ element }">
                <div>
                  <!-- 大题标题块（可拖拽、可内联编辑） -->
                  <div
                    v-if="element.kind === 'section'"
                    class="group relative pl-8 pr-16 mt-6 mb-3 first:mt-0"
                  >
                    <div
                      class="drag-handle absolute left-0 top-1 cursor-move opacity-0 group-hover:opacity-60 hover:!opacity-100 transition-opacity"
                    >
                      <GripVertical class="h-5 w-5 text-muted-foreground" />
                    </div>

                    <Input
                      v-if="editingSectionId === element.ownerId"
                      v-model="editSectionDraft"
                      class="h-9 text-lg font-bold"
                      autofocus
                      @keydown.enter="commitEditSection"
                      @keydown.esc="editingSectionId = null"
                      @blur="commitEditSection"
                    />
                    <template v-else>
                      <h2
                        class="text-lg font-bold text-foreground cursor-text hover:text-primary transition-colors"
                        title="点击编辑标题"
                        @click="startEditSection(element.ownerId, element.title)"
                      >
                        {{ element.title }}
                      </h2>
                      <Button
                        variant="ghost"
                        size="icon"
                        class="absolute right-2 top-0 h-7 w-7 text-destructive hover:text-destructive opacity-0 group-hover:opacity-100 transition-opacity"
                        title="删除大题标题"
                        @click="removeSection(element.ownerId)"
                      >
                        <Trash2 class="h-4 w-4" />
                      </Button>
                    </template>
                  </div>

                  <!-- 题目块 -->
                  <div v-else class="group/insert relative">
                    <!-- 悬停：在此题前插入大题 -->
                    <div
                      class="absolute -top-3 left-0 right-0 z-10 flex justify-center opacity-0 group-hover/insert:opacity-100 transition-opacity"
                    >
                      <Button
                        variant="secondary"
                        size="sm"
                        class="h-6 px-2 text-xs shadow-sm"
                        @click="openInsertSection(element.item)"
                      >
                        <Heading2 class="mr-1 h-3 w-3" /> 在此处插入大题
                      </Button>
                    </div>
                    <PaperQuestionCard
                      :item="element.item"
                      :number="displayNumbers[element.id]"
                      @remove="onRemoveItem(element.item)"
                      @view-detail="viewQuestion(element.item)"
                    />
                  </div>
                </div>
              </template>
            </draggable>
          </div>

          <div
            v-else
            class="bg-background rounded-lg shadow-sm border flex flex-col items-center justify-center py-16 text-center"
          >
            <p class="text-muted-foreground mb-4">还没有题目</p>
            <Button @click="goToLibrary">
              <Plus class="mr-2 h-4 w-4" /> 去题库添加题目
            </Button>
          </div>
        </div>
      </div>

      <!-- Right: config panel -->
      <div class="hidden md:block w-80 overflow-y-auto bg-muted/20 border-l">
        <div class="p-4 space-y-6">
          <Card>
            <CardHeader class="pb-3">
              <CardTitle class="text-base">基本信息</CardTitle>
            </CardHeader>
            <CardContent class="space-y-4">
              <div class="space-y-2">
                <Label>标题</Label>
                <Input v-model="paper.title" />
              </div>
              <div class="space-y-2">
                <Label>科目</Label>
                <Select v-model="paper.subject_id" @update:model-value="savePaperInfo">
                  <SelectTrigger>
                    <SelectValue placeholder="选择科目" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem v-for="s in subjects" :key="s.id" :value="s.id">
                      {{ s.name }}
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div class="space-y-2">
                <Label>描述</Label>
                <Textarea v-model="paper.description" rows="3" @blur="savePaperInfo" />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader class="pb-3">
              <CardTitle class="text-base">题目统计</CardTitle>
            </CardHeader>
            <CardContent class="space-y-3">
              <div v-if="typeStatList.length === 0" class="text-sm text-muted-foreground">
                暂无题目
              </div>
              <div
                v-for="t in typeStatList"
                :key="t.label"
                class="flex items-center justify-between text-sm"
              >
                <span class="text-muted-foreground">{{ t.label }}</span>
                <Badge variant="secondary">{{ t.count }}</Badge>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  </div>

  <!-- Export dialog -->
  <Dialog v-model:open="exportOpen">
    <DialogContent class="sm:max-w-[480px]">
      <DialogHeader>
        <DialogTitle>导出试卷</DialogTitle>
      </DialogHeader>
      <div class="space-y-4 py-2">
        <div class="space-y-2">
          <Label>导出格式</Label>
          <Select v-model="exportForm.format">
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="docx">Word (.docx)</SelectItem>
              <SelectItem value="latex">LaTeX (.zip)</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div class="space-y-2">
          <Label>包含内容</Label>
          <div class="flex flex-wrap gap-4">
            <div class="flex items-center space-x-2">
              <Checkbox id="ex_answer" v-model="exportForm.include_answer" />
              <Label for="ex_answer" class="font-normal">标准答案</Label>
            </div>
            <div class="flex items-center space-x-2">
              <Checkbox id="ex_analysis" v-model="exportForm.include_analysis" />
              <Label for="ex_analysis" class="font-normal">分析</Label>
            </div>
            <div class="flex items-center space-x-2">
              <Checkbox id="ex_explanation" v-model="exportForm.include_explanation" />
              <Label for="ex_explanation" class="font-normal">解析</Label>
            </div>
            <div class="flex items-center space-x-2">
              <Checkbox id="ex_summary" v-model="exportForm.include_summary" />
              <Label for="ex_summary" class="font-normal">总结</Label>
            </div>
            <div class="flex items-center space-x-2">
              <Checkbox id="ex_source" v-model="exportForm.include_source" />
              <Label for="ex_source" class="font-normal">来源</Label>
            </div>
          </div>
        </div>
      </div>
      <DialogFooter>
        <Button variant="outline" @click="exportOpen = false">取消</Button>
        <Button :disabled="exporting || items.length === 0" @click="doExport">
          <Loader2 v-if="exporting" class="mr-2 h-4 w-4 animate-spin" />
          <FileDown v-else class="mr-2 h-4 w-4" />
          生成并下载
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>

  <!-- Insert section dialog -->
  <Dialog v-model:open="insertSectionOpen">
    <DialogContent class="sm:max-w-[400px]">
      <DialogHeader>
        <DialogTitle>插入大题标题</DialogTitle>
      </DialogHeader>
      <div class="space-y-4 py-2">
        <div class="space-y-2">
          <Label>标题内容</Label>
          <Input
            v-model="newSectionTitle"
            placeholder="例如：一、选择题"
            autofocus
            @keydown.enter="doInsertSection"
          />
          <p class="text-xs text-muted-foreground">
            将作为该题所在大题的标题
          </p>
        </div>
      </div>
      <DialogFooter>
        <Button variant="outline" @click="insertSectionOpen = false">取消</Button>
        <Button :disabled="!newSectionTitle.trim()" @click="doInsertSection">
          <Heading2 class="mr-2 h-4 w-4" />
          插入
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>

  <!-- Question detail side panel -->
  <PaperQuestionDetailSheet
    v-model:open="detailSheetOpen"
    :question-id="detailQuestionId"
    :subjects="subjects || []"
    :knowledge-points="knowledgePoints || []"
    @updated="load"
  />
</template>
