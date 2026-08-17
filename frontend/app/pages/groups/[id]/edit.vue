<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useDebounceFn } from '@vueuse/core'
import { Button } from '@/components/ui/button'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Separator } from '@/components/ui/separator'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { ArrowLeft, Loader2, CheckCircle, Plus } from '@lucide/vue'
import { toast } from 'vue-sonner'
import BlockCanvas from '@/components/canvas/BlockCanvas.vue'
import { toEditorBlock, toBlockWrite, type EditorBlock } from '@/components/canvas/blockRegistry'
import PaperQuestionDetailSheet from '@/components/PaperQuestionDetailSheet.vue'
import { useCompositions } from '~/composables/useCompositions'
import type { CompositionDetail, Subject, KnowledgePoint } from '~/types'

const route = useRoute()
const router = useRouter()
const pubId = Number(route.params.id)

const { get, update, saveBlocks } = useCompositions()
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

const canvasContext = { pubType: 'question_group' as const, showAnswers: true }

const difficultyOptions = [
  { value: 1, label: '★ 容易' },
  { value: 2, label: '★★ 较易' },
  { value: 3, label: '★★★ 中等' },
  { value: 4, label: '★★★★ 较难' },
  { value: 5, label: '★★★★★ 困难' },
]

const load = async () => {
  loading.value = true
  try {
    const data = await get(pubId)
    publication.value = data
    blocks.value = data.blocks.map(toEditorBlock)
  } catch {
    toast.error('加载题组失败')
    router.push('/library?type=group')
  } finally {
    loading.value = false
  }
}

await load()

const questionCount = computed(
  () => blocks.value.filter((b) => b.block_type === 'question').length,
)

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

const onCanvasChange = () => persistBlocks()

const saveInfo = useDebounceFn(async () => {
  if (!publication.value) return
  saving.value = true
  savingStatus.value = '保存中...'
  try {
    await update(pubId, {
      title: publication.value.title,
      description: publication.value.description ?? null,
      difficulty: publication.value.difficulty ?? null,
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

const goToLibrary = () => router.push('/questions')

watch(
  () => publication.value?.title,
  (v, old) => { if (old !== undefined && v !== old) saveInfo() },
)
watch(
  () => publication.value?.difficulty,
  (v, old) => { if (old !== undefined && v !== old) saveInfo() },
)
</script>

<template>
  <div v-if="loading" class="flex-1 flex items-center justify-center">
    <Loader2 class="h-8 w-8 animate-spin text-muted-foreground" />
  </div>

  <div v-else-if="publication" class="flex flex-col h-[calc(100vh-0px)]">
    <div class="border-b bg-background sticky top-0 z-10">
      <div class="flex items-center justify-between px-4 py-3 gap-3">
        <div class="flex items-center gap-3 min-w-0">
          <Button variant="ghost" size="icon" @click="router.push('/library?type=group')">
            <ArrowLeft class="h-4 w-4" />
          </Button>
          <div class="min-w-0">
            <h1 class="text-lg font-semibold truncate">{{ publication.title }}</h1>
            <p class="text-sm text-muted-foreground">题组 · {{ questionCount }} 题</p>
          </div>
        </div>
        <div class="text-sm text-muted-foreground flex items-center gap-1.5 min-w-[80px]">
          <Loader2 v-if="saving" class="h-3 w-3 animate-spin" />
          <CheckCircle v-else-if="saved" class="h-3 w-3 text-green-600" />
          <span>{{ savingStatus }}</span>
        </div>
      </div>
    </div>

    <div class="flex flex-1 overflow-hidden">
      <div class="flex-1 overflow-y-auto bg-muted/30">
        <div class="p-6 max-w-3xl mx-auto">
          <div class="flex items-center justify-between mb-4">
            <div class="text-sm text-muted-foreground">教学微模块：讲解 + 例题/练习</div>
            <Button variant="outline" size="sm" @click="goToLibrary">
              <Plus class="mr-2 h-4 w-4" /> 去题库添加
            </Button>
          </div>

          <div
            v-if="blocks.length > 0"
            class="bg-background rounded-lg shadow-sm border px-10 py-8"
          >
            <BlockCanvas
              v-model="blocks"
              :context="canvasContext"
              @change="onCanvasChange"
              @view-detail="viewQuestion"
            />
          </div>

          <div
            v-else
            class="bg-background rounded-lg shadow-sm border flex flex-col items-center justify-center py-16 text-center"
          >
            <p class="text-muted-foreground mb-4">还没有内容，先写一段讲解或去题库添加题目</p>
            <Button @click="goToLibrary">
              <Plus class="mr-2 h-4 w-4" /> 去题库添加题目
            </Button>
          </div>
        </div>
      </div>

      <div class="hidden md:block w-80 overflow-y-auto bg-muted/20 border-l">
        <div class="p-4 space-y-6">
          <Card>
            <CardHeader class="pb-3">
              <CardTitle class="text-base">题组信息</CardTitle>
            </CardHeader>
            <CardContent class="space-y-4">
              <div class="space-y-2">
                <Label>标题</Label>
                <Input v-model="publication.title" />
              </div>
              <div class="space-y-2">
                <Label>科目</Label>
                <Select v-model="publication.subject_id" disabled>
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
                <Label>难度</Label>
                <Select v-model="publication.difficulty">
                  <SelectTrigger>
                    <SelectValue placeholder="选择难度" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem v-for="d in difficultyOptions" :key="d.value" :value="d.value">
                      {{ d.label }}
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div class="space-y-2">
                <Label>描述</Label>
                <Textarea v-model="publication.description" rows="3" @blur="saveInfo" />
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  </div>

  <PaperQuestionDetailSheet
    v-model:open="detailSheetOpen"
    :question-id="detailQuestionId"
    :subjects="subjects || []"
    :knowledge-points="knowledgePoints || []"
    @updated="load"
  />
</template>
