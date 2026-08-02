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
  ArrowLeft, Download, Loader2, CheckCircle, Plus, FileDown, Trash2,
} from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import PaperQuestionCard from '@/components/PaperQuestionCard.vue'
import { usePapers } from '~/composables/usePapers'
import type { PaperDetail, PaperItem, Subject } from '~/types'

const route = useRoute()
const router = useRouter()
const paperId = Number(route.params.id)

const { get, update, removeItem, reorder, download, updateItem } = usePapers()
const { data: subjects } = await useAPI<Subject[]>('/subjects')

const paper = ref<PaperDetail | null>(null)
const items = ref<PaperItem[]>([])
const loading = ref(true)

const saving = ref(false)
const saved = ref(false)
const savingStatus = ref('')

const load = async () => {
  loading.value = true
  try {
    const data = await get(paperId)
    paper.value = data
    items.value = [...data.items]
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
  saving.value = true
  savingStatus.value = '保存中...'
  try {
    await reorder(paperId, items.value.map((i) => i.id))
    saved.value = true
    savingStatus.value = '已保存'
    setTimeout(() => { saved.value = false }, 3000)
  } catch {
    savingStatus.value = '排序保存失败'
    await load()
  } finally {
    saving.value = false
  }
}

const onRemoveItem = async (item: PaperItem) => {
  const prev = [...items.value]
  items.value = items.value.filter((i) => i.id !== item.id)
  try {
    await removeItem(paperId, item.id)
    if (paper.value) paper.value.question_count = items.value.length
  } catch {
    toast.error('移除失败')
    items.value = prev
  }
}

const onUpdateSection = async (item: PaperItem, value: string | null) => {
  const prev = item.section_title ?? null
  item.section_title = value
  try {
    await updateItem(paperId, item.id, { section_title: value })
  } catch {
    toast.error('保存大题标题失败')
    item.section_title = prev
  }
}

const viewQuestion = (item: PaperItem) => {
  if (item.question) {
    window.open(`/questions?id=${item.question.id}`, '_blank')
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
      <!-- Left: question list -->
      <div class="flex-1 overflow-y-auto">
        <div class="p-4 space-y-3 max-w-3xl mx-auto">
          <div class="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
            <div class="text-sm text-muted-foreground">共 {{ items.length }} 道题目</div>
            <Button variant="outline" size="sm" @click="goToLibrary">
              <Plus class="mr-2 h-4 w-4" /> 去题库添加
            </Button>
          </div>

          <draggable
            v-if="items.length > 0"
            v-model="items"
            item-key="id"
            handle=".drag-handle"
            :animation="200"
            class="space-y-3"
            @end="onDragEnd"
          >
            <template #item="{ element, index }">
              <PaperQuestionCard
                :item="element"
                :index="index"
                @remove="onRemoveItem(element)"
                @view-detail="viewQuestion(element)"
                @update-section="onUpdateSection(element, $event)"
              />
            </template>
          </draggable>

          <div v-else class="flex flex-col items-center justify-center py-16 text-center">
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
              <CardTitle class="text-base">试卷信息</CardTitle>
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
</template>
