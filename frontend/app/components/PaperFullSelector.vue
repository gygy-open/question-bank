<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Search, Check, Plus, Loader2 } from '@lucide/vue'
import { toast } from 'vue-sonner'
import { useCompositions } from '@/composables/useCompositions'
import { formatRelativeTime } from '@/lib/utils'
import type { Composition } from '~/types'

const props = defineProps<{
  open: boolean
  questionIds: number[]
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  added: []
}>()

const { list, create, appendQuestions } = useCompositions()
const { currentSubjectId } = useSubjectContext()

const loading = ref(false)
const submitting = ref(false)
const papers = ref<Composition[]>([])
const searchQuery = ref('')
const selectedPaperId = ref<number | null>(null)

const filteredPapers = computed(() => {
  if (!searchQuery.value) return papers.value
  const q = searchQuery.value.toLowerCase()
  return papers.value.filter((p) => p.title.toLowerCase().includes(q))
})

const loadPapers = async () => {
  loading.value = true
  try {
    papers.value = await list({ comp_type: 'exam_paper', subject_id: currentSubjectId.value, sort: 'updated_desc' })
  } catch {
    toast.error('加载试卷失败')
  } finally {
    loading.value = false
  }
}

watch(
  () => props.open,
  (v) => {
    if (v) {
      selectedPaperId.value = null
      searchQuery.value = ''
      loadPapers()
    }
  }
)

const confirmAdd = async () => {
  if (!selectedPaperId.value) return
  submitting.value = true
  try {
    const paper = papers.value.find((p) => p.id === selectedPaperId.value)
    await appendQuestions(selectedPaperId.value, props.questionIds)
    toast.success(`已将 ${props.questionIds.length} 道题加入《${paper?.title}》`)
    emit('added')
    emit('update:open', false)
  } catch {
    toast.error('加入失败')
  } finally {
    submitting.value = false
  }
}

const createNewPaper = async () => {
  submitting.value = true
  try {
    const paper = await create({ title: `新试卷 ${new Date().toLocaleDateString()}`, comp_type: 'exam_paper' })
    await appendQuestions(paper.id, props.questionIds)
    toast.success(`已创建并加入 ${props.questionIds.length} 道题`)
    emit('added')
    emit('update:open', false)
  } catch {
    toast.error('创建失败')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogContent class="max-w-2xl">
      <DialogHeader>
        <DialogTitle>选择试卷</DialogTitle>
        <DialogDescription>
          将 {{ questionIds.length }} 道题加入试卷
        </DialogDescription>
      </DialogHeader>

      <div class="relative">
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input v-model="searchQuery" placeholder="搜索试卷标题..." class="pl-9" />
      </div>

      <div v-if="loading" class="h-[360px] flex items-center justify-center">
        <Loader2 class="h-6 w-6 animate-spin text-muted-foreground" />
      </div>

      <ScrollArea v-else class="h-[360px] pr-3">
        <div class="space-y-2">
          <button
            v-for="paper in filteredPapers"
            :key="paper.id"
            :class="[
              'w-full flex items-start gap-3 p-3 rounded-lg border-2 transition-all text-left',
              selectedPaperId === paper.id
                ? 'border-primary bg-primary/5'
                : 'border-transparent hover:border-muted hover:bg-muted/50',
            ]"
            @click="selectedPaperId = paper.id"
          >
            <div class="flex-shrink-0 mt-1">
              <div
                :class="[
                  'w-5 h-5 rounded-full border-2 flex items-center justify-center transition-colors',
                  selectedPaperId === paper.id ? 'border-primary bg-primary' : 'border-muted-foreground',
                ]"
              >
                <Check v-if="selectedPaperId === paper.id" class="h-3 w-3 text-primary-foreground" />
              </div>
            </div>
            <div class="flex-1 min-w-0">
              <div class="flex items-center justify-between gap-2">
                <div class="font-medium truncate">{{ paper.title }}</div>
                <Badge v-if="paper.status === 'archived'" variant="secondary">已归档</Badge>
              </div>
              <div class="text-sm text-muted-foreground mt-1">
                {{ paper.block_count }} 项 · {{ formatRelativeTime(paper.updated_at) }}
              </div>
            </div>
          </button>

          <div v-if="filteredPapers.length === 0" class="py-8 text-center text-sm text-muted-foreground">
            没有匹配的试卷
          </div>

          <button
            class="w-full flex items-center gap-3 p-3 rounded-lg border-2 border-dashed border-muted-foreground/30 hover:border-primary hover:bg-primary/5 transition-all"
            @click="createNewPaper"
          >
            <div class="w-5 h-5 rounded-full bg-primary/10 flex items-center justify-center">
              <Plus class="h-3 w-3 text-primary" />
            </div>
            <div class="text-sm font-medium text-primary">新建试卷</div>
          </button>
        </div>
      </ScrollArea>

      <DialogFooter>
        <Button variant="outline" @click="emit('update:open', false)">取消</Button>
        <Button :disabled="!selectedPaperId || submitting" @click="confirmAdd">
          <Loader2 v-if="submitting" class="mr-2 h-4 w-4 animate-spin" />
          确定
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
