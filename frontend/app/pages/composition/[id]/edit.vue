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
import {
  Accordion, AccordionItem, AccordionContent, AccordionTrigger,
} from '@/components/ui/accordion'
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger,
} from '@/components/ui/sheet'
import {
  ArrowLeft, Download, Loader2, CheckCircle, FileDown, Settings,
} from '@lucide/vue'
import { toast } from 'vue-sonner'
import BlockCanvas from '@/components/canvas/BlockCanvas.vue'
import DocumentDisplaySettings from '@/components/canvas/DocumentDisplaySettings.vue'
import { toEditorBlock, toBlockWrite, type EditorBlock } from '@/components/canvas/blockRegistry'
import PaperQuestionDetailSheet from '@/components/PaperQuestionDetailSheet.vue'
import { useCompositions } from '~/composables/useCompositions'
import type {
  CompositionDetail, CompositionSettings, DisplayPolicy, NumberingPolicy, ScoringPolicy, Subject, KnowledgePoint,
} from '~/types'

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

// 题块按文档级显示策略解析 (所见即所得)
const canvasContext = computed(() => ({
  documentDisplay: publication.value?.meta_data?.display ?? null,
  documentNumbering: publication.value?.meta_data?.numbering ?? null,
  documentScoring: publication.value?.meta_data?.scoring ?? null,
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

// Prefer real browser back navigation; fall back only when there's no prior history (e.g. direct link).
const goBack = () => {
  if (window.history.state?.back) {
    router.back()
  } else {
    router.push('/library?scope=personal')
  }
}

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
})

// 文档级显示策略变更即持久化 (所见即所得)
const onDisplayChange = async (display: DisplayPolicy) => {
  if (!publication.value) return
  const meta: CompositionSettings = { ...(publication.value.meta_data || {}), display }
  publication.value.meta_data = meta
  try {
    await update(pubId, { meta_data: meta })
    toast.success('显示设置已更新')
  } catch {
    toast.error('显示设置保存失败')
  }
}

// 文档级编号策略变更即持久化
const onNumberingChange = async (numbering: NumberingPolicy) => {
  if (!publication.value) return
  const meta: CompositionSettings = { ...(publication.value.meta_data || {}), numbering }
  publication.value.meta_data = meta
  try {
    await update(pubId, { meta_data: meta })
    toast.success('编号设置已更新')
  } catch {
    toast.error('编号设置保存失败')
  }
}

// 文档级赋分策略变更即持久化 (影响编辑器内展示与导出是否打印分值)
const onScoringChange = async (scoring: ScoringPolicy) => {
  if (!publication.value) return
  const meta: CompositionSettings = { ...(publication.value.meta_data || {}), scoring }
  publication.value.meta_data = meta
  try {
    await update(pubId, { meta_data: meta })
    toast.success('赋分设置已更新')
  } catch {
    toast.error('赋分设置保存失败')
  }
}

const doExport = async () => {
  if (!publication.value) return
  exporting.value = true
  try {
    const blob = await download(pubId, {
      title: publication.value.title,
      format: exportForm.value.format,
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
          <Button variant="ghost" size="icon" @click="goBack">
            <ArrowLeft class="h-4 w-4" />
          </Button>
          <div class="min-w-0">
            <!-- 系统层文档名 (库列表/搜索用), 与正文标题 block 解耦 -->
            <input
              v-model="publication.title"
              class="w-full max-w-xs truncate rounded-md bg-transparent px-1 text-lg font-semibold outline-none focus:bg-muted/40"
              placeholder="无标题"
              @blur="savePaperInfo"
            />
          </div>
        </div>

        <div class="flex items-center gap-2">
          <div class="text-sm text-muted-foreground flex items-center gap-1.5 min-w-[80px]">
            <Loader2 v-if="saving" class="h-3 w-3 animate-spin" />
            <CheckCircle v-else-if="saved" class="h-3 w-3 text-green-600" />
            <span>{{ savingStatus }}</span>
          </div>
          <Separator orientation="vertical" class="h-6" />
          <!-- 桌面端设置常驻右侧栏, 这里只给窄屏一个入口 -->
          <Sheet>
            <SheetTrigger as-child>
              <Button variant="outline" size="icon" class="md:hidden">
                <Settings class="h-4 w-4" />
              </Button>
            </SheetTrigger>
            <SheetContent side="right" class="w-80 overflow-y-auto sm:max-w-sm">
              <SheetHeader>
                <SheetTitle>文档设置</SheetTitle>
              </SheetHeader>
              <div class="px-4 pb-4">
                <DocumentDisplaySettings
                  :model-value="publication.meta_data?.display"
                  :numbering="publication.meta_data?.numbering"
                  :scoring="publication.meta_data?.scoring"
                  @update:model-value="onDisplayChange"
                  @update:numbering="onNumberingChange"
                  @update:scoring="onScoringChange"
                />
              </div>
            </SheetContent>
          </Sheet>
          <Button size="sm" @click="exportOpen = true">
            <Download class="mr-2 h-4 w-4" /> 导出
          </Button>
        </div>
      </div>
    </div>

    <!-- Main -->
    <div class="flex flex-1 overflow-hidden">
      <!-- Left: paper preview / canvas -->
      <div class="flex-1 overflow-y-auto bg-background">
        <div class="p-6 max-w-4xl mx-auto">
          <div class="px-10 py-8">
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

          <Accordion type="single" collapsible default-value="display" class="rounded-lg border bg-background px-3">
            <AccordionItem value="display" class="border-none">
              <AccordionTrigger class="py-3 text-base font-semibold hover:no-underline">
                文档设置
              </AccordionTrigger>
              <AccordionContent class="pb-3">
                <DocumentDisplaySettings
                  :model-value="publication.meta_data?.display"
                  :numbering="publication.meta_data?.numbering"
                  :scoring="publication.meta_data?.scoring"
                  @update:model-value="onDisplayChange"
                  @update:numbering="onNumberingChange"
                  @update:scoring="onScoringChange"
                />
              </AccordionContent>
            </AccordionItem>
          </Accordion>
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
