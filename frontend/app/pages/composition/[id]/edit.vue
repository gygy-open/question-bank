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
  ArrowLeft, Download, Loader2, CheckCircle, FileDown,
} from '@lucide/vue'
import { toast } from 'vue-sonner'
import BlockCanvas from '@/components/canvas/BlockCanvas.vue'
import DocumentDisplaySettings from '@/components/canvas/DocumentDisplaySettings.vue'
import { toEditorBlock, toBlockWrite, type EditorBlock } from '@/components/canvas/blockRegistry'
import PaperQuestionDetailSheet from '@/components/PaperQuestionDetailSheet.vue'
import { useCompositions } from '~/composables/useCompositions'
import type { CompositionDetail, CompositionSettings, DisplayPolicy, Subject, KnowledgePoint } from '~/types'

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
  } catch {
    /* 非关键路径, 静默失败 */
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
            <h1 class="text-lg font-semibold truncate">{{ publication.title }}</h1>
          </div>
        </div>

        <div class="flex items-center gap-2">
          <div class="text-sm text-muted-foreground flex items-center gap-1.5 min-w-[80px]">
            <Loader2 v-if="saving" class="h-3 w-3 animate-spin" />
            <CheckCircle v-else-if="saved" class="h-3 w-3 text-green-600" />
            <span>{{ savingStatus }}</span>
          </div>
          <Separator orientation="vertical" class="h-6" />
          <DocumentDisplaySettings
            :model-value="publication.meta_data?.display"
            @update:model-value="onDisplayChange"
          />
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
