<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useDebounceFn } from '@vueuse/core'
import { Button } from '@/components/ui/button'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import { Checkbox } from '@/components/ui/checkbox'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import {
  ArrowLeft, Download, Loader2, CheckCircle, FileDown,
} from '@lucide/vue'
import { toast } from 'vue-sonner'
import BlockCanvas from '@/components/canvas/BlockCanvas.vue'
import { toEditorBlock, toBlockWrite, type EditorBlock } from '@/components/canvas/blockRegistry'
import PaperQuestionDetailSheet from '@/components/PaperQuestionDetailSheet.vue'
import { useCompositions } from '~/composables/useCompositions'
import type { CompositionDetail, Subject, KnowledgePoint, CompType } from '~/types'

const route = useRoute()
const router = useRouter()
const pubId = Number(route.params.id)

const { get, update, saveBlocks, download } = useCompositions()
const { data: subjects } = await useAPI<Subject[]>('/subjects')
const { data: knowledgePoints } = await useAPI<KnowledgePoint[]>('/knowledge-points', {
  query: { limit: -1 },
})

const publication = ref<CompositionDetail | null>(null)
const blocks = ref<EditorBlock[]>([])
const loading = ref(true)

const saving = ref(false)
const saved = ref(false)
const savingStatus = ref('')

const detailSheetOpen = ref(false)
const detailQuestionId = ref<number | null>(null)

// 教学模块需展示答案便于编辑核对; 讲义/试卷默认不展示
const canvasContext = computed(() => ({
  pubType: (publication.value?.comp_type ?? 'exam_paper') as CompType,
  showAnswers: publication.value?.comp_type === 'question_group',
  compId: pubId,
}))

const load = async () => {
  loading.value = true
  try {
    const data = await get(pubId)
    publication.value = data
    blocks.value = data.blocks.map(toEditorBlock)
  } catch {
    toast.error('加载试卷失败')
    router.push('/library?scope=personal')
  } finally {
    loading.value = false
  }
}

await load()

const questionCount = computed(
  () => blocks.value.filter((b) => b.block_type === 'question').length,
)

const typeStatList = computed(() => {
  const labels: Record<string, string> = {
    single_choice: '单选题', multiple_choice: '多选题', true_false: '判断题',
    fill_in_the_blank: '填空题', free_response: '解答题',
  }
  const byType: Record<string, number> = {}
  for (const b of blocks.value) {
    if (b.block_type !== 'question' || !b.question) continue
    byType[b.question.q_type] = (byType[b.question.q_type] || 0) + 1
  }
  return Object.entries(byType).map(([k, v]) => ({ label: labels[k] || k, count: v }))
})

const persistBlocks = useDebounceFn(async () => {
  if (!publication.value) return
  saving.value = true
  savingStatus.value = '保存中...'
  try {
    await saveBlocks(pubId, blocks.value.map(toBlockWrite))
    saved.value = true
    savingStatus.value = '已保存'
    setTimeout(() => { saved.value = false }, 3000)
  } catch {
    savingStatus.value = '保存失败'
  } finally {
    saving.value = false
  }
}, 1200)

const onCanvasChange = () => {
  persistBlocks()
}

const savePaperInfo = useDebounceFn(async () => {
  if (!publication.value) return
  saving.value = true
  savingStatus.value = '保存中...'
  try {
    await update(pubId, {
      title: publication.value.title,
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

const viewQuestion = (block: EditorBlock) => {
  if (block.question) {
    detailQuestionId.value = block.question.id
    detailSheetOpen.value = true
  }
}

// --- Export ---
const exportOpen = ref(false)
const exporting = ref(false)
const exportForm = ref({
  format: 'docx' as 'docx' | 'latex',
  content_position: 'after_question' as 'after_question' | 'end_of_paper' | 'hidden',
  include_answer: false,
  include_analysis: false,
  include_explanation: false,
  include_summary: false,
  include_source: false,
})

const contentPositionEnabled = computed(() => exportForm.value.content_position !== 'hidden')

const doExport = async () => {
  if (!publication.value) return
  exporting.value = true
  try {
    const blob = await download(pubId, {
      title: publication.value.title,
      ...exportForm.value,
    })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    const ext = exportForm.value.format === 'latex' ? 'zip' : exportForm.value.format
    link.setAttribute('download', `${publication.value.title}.${ext}`)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
    exportOpen.value = false
    toast.success('已导出')
  } catch {
    toast.error('导出失败')
  } finally {
    exporting.value = false
  }
}

watch(
  () => publication.value?.title,
  (v, old) => { if (old !== undefined && v !== old) savePaperInfo() },
)
</script>

<template>
  <div v-if="loading" class="flex-1 flex items-center justify-center">
    <Loader2 class="h-8 w-8 animate-spin text-muted-foreground" />
  </div>

  <div v-else-if="publication" class="flex flex-col h-[calc(100vh-0px)]">
    <!-- Top toolbar -->
    <div class="border-b bg-background sticky top-0 z-10">
      <div class="flex items-center justify-between px-4 py-3 gap-3">
        <div class="flex items-center gap-3 min-w-0">
          <Button variant="ghost" size="icon" @click="router.push('/library?scope=personal')">
            <ArrowLeft class="h-4 w-4" />
          </Button>
          <div class="min-w-0">
            <h1 class="text-lg font-semibold truncate">{{ publication.title }}</h1>
            <p class="text-sm text-muted-foreground">{{ questionCount }} 题</p>
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
      <!-- Left: paper preview / canvas -->
      <div class="flex-1 overflow-y-auto bg-muted/30">
        <div class="p-6 max-w-3xl mx-auto">
          <div class="bg-background rounded-lg shadow-sm border px-10 py-8">
            <!-- 抬头: 标题直接在此编辑 -->
            <div class="text-center mb-6 pb-4 border-b">
              <input
                v-model="publication.title"
                class="w-full bg-transparent text-center text-2xl font-bold outline-none focus:bg-muted/40 rounded-md px-2 py-1"
                placeholder="无标题"
                @blur="savePaperInfo"
              />
            </div>

            <BlockCanvas
              v-model="blocks"
              :context="canvasContext"
              @change="onCanvasChange"
              @view-detail="viewQuestion"
            />

            <p v-if="blocks.length === 0" class="mt-4 text-center text-sm text-muted-foreground">
              还没有内容，点击上方「插入内容」或悬停在块之间开始编辑
            </p>
          </div>
        </div>
      </div>

      <!-- Right: config panel -->
      <div class="hidden md:block w-80 overflow-y-auto bg-muted/20 border-l">
        <div class="p-4 space-y-6">
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

        <Separator />

        <div class="space-y-3">
          <Label>附加内容显示位置</Label>
          <RadioGroup v-model="exportForm.content_position">
            <div class="flex items-center space-x-2">
              <RadioGroupItem id="pos_after" value="after_question" />
              <Label for="pos_after" class="font-normal cursor-pointer">
                <div class="flex flex-col">
                  <span>题目后</span>
                  <span class="text-xs text-muted-foreground">每题后紧跟答案和解析</span>
                </div>
              </Label>
            </div>
            <div class="flex items-center space-x-2">
              <RadioGroupItem id="pos_end" value="end_of_paper" />
              <Label for="pos_end" class="font-normal cursor-pointer">
                <div class="flex flex-col">
                  <span>卷尾附录</span>
                  <span class="text-xs text-muted-foreground">统一放在试卷末尾</span>
                </div>
              </Label>
            </div>
            <div class="flex items-center space-x-2">
              <RadioGroupItem id="pos_hidden" value="hidden" />
              <Label for="pos_hidden" class="font-normal cursor-pointer">
                <div class="flex flex-col">
                  <span>不显示</span>
                  <span class="text-xs text-muted-foreground">仅导出题目内容</span>
                </div>
              </Label>
            </div>
          </RadioGroup>
        </div>

        <div v-if="contentPositionEnabled" class="space-y-2">
          <Label>包含项目</Label>
          <div class="flex flex-wrap gap-4">
            <div class="flex items-center space-x-2">
              <Checkbox id="ex_answer" v-model="exportForm.include_answer" />
              <Label for="ex_answer" class="font-normal cursor-pointer">标准答案</Label>
            </div>
            <div class="flex items-center space-x-2">
              <Checkbox id="ex_analysis" v-model="exportForm.include_analysis" />
              <Label for="ex_analysis" class="font-normal cursor-pointer">分析</Label>
            </div>
            <div class="flex items-center space-x-2">
              <Checkbox id="ex_explanation" v-model="exportForm.include_explanation" />
              <Label for="ex_explanation" class="font-normal cursor-pointer">解析</Label>
            </div>
            <div class="flex items-center space-x-2">
              <Checkbox id="ex_summary" v-model="exportForm.include_summary" />
              <Label for="ex_summary" class="font-normal cursor-pointer">总结</Label>
            </div>
            <div class="flex items-center space-x-2">
              <Checkbox id="ex_source" v-model="exportForm.include_source" />
              <Label for="ex_source" class="font-normal cursor-pointer">来源</Label>
            </div>
          </div>
        </div>
      </div>
      <DialogFooter>
        <Button variant="outline" @click="exportOpen = false">取消</Button>
        <Button :disabled="exporting || blocks.length === 0" @click="doExport">
          <Loader2 v-if="exporting" class="mr-2 h-4 w-4 animate-spin" />
          <FileDown v-else class="mr-2 h-4 w-4" />
          生成并下载
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
