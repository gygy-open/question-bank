<script setup lang="ts">
import { ref } from 'vue'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ShoppingBasket, Clock, Plus, List, Loader2, CheckCircle } from '@lucide/vue'
import { toast } from 'vue-sonner'
import { usePapers } from '@/composables/usePapers'
import type { Paper } from '~/types'

const props = defineProps<{
  questionId: number
}>()

const { list, create, addItems } = usePapers()
const { currentSubjectId } = useSubjectContext()

const open = ref(false)
const loading = ref(false)
const papers = ref<Paper[]>([])
const total = ref(0)

const showFull = ref(false)

const loadPapers = async () => {
  loading.value = true
  try {
    const data = await list({ subject_id: currentSubjectId.value, status: 'draft', sort: 'updated_desc' })
    papers.value = data
    total.value = data.length
  } catch {
    toast.error('加载试卷失败')
  } finally {
    loading.value = false
  }
}

const onOpenChange = (value: boolean) => {
  open.value = value
  if (value) loadPapers()
}

const addToPaper = async (paper: Paper) => {
  try {
    await addItems(paper.id, [props.questionId])
    toast.success(`已加入《${paper.title}》`)
    open.value = false
  } catch {
    toast.error('加入失败')
  }
}

const createAndAdd = async () => {
  try {
    const paper = await create({ title: `新试卷 ${new Date().toLocaleDateString()}` })
    await addItems(paper.id, [props.questionId])
    toast.success(`已创建并加入《${paper.title}》`)
    open.value = false
  } catch {
    toast.error('创建失败')
  }
}

const goToAllPapers = () => {
  open.value = false
  navigateTo('/papers')
}

const onKey = (e: KeyboardEvent) => {
  const idx = ['1', '2', '3'].indexOf(e.key)
  if (idx >= 0 && papers.value[idx]) {
    e.preventDefault()
    addToPaper(papers.value[idx])
  }
}
</script>

<template>
  <Popover :open="open" @update:open="onOpenChange">
    <PopoverTrigger as-child>
      <Button
        variant="ghost"
        size="icon"
        class="h-8 w-8 text-muted-foreground"
        title="加入试卷"
      >
        <ShoppingBasket class="h-4 w-4" />
      </Button>
    </PopoverTrigger>

    <PopoverContent class="w-80 p-0" align="end" @keydown="onKey">
      <div v-if="loading" class="p-6 flex items-center justify-center">
        <Loader2 class="h-5 w-5 animate-spin text-muted-foreground" />
      </div>

      <div v-else class="divide-y">
        <div class="p-2 space-y-1">
          <div class="px-2 py-1 text-xs font-medium text-muted-foreground flex items-center gap-1">
            <Clock class="h-3 w-3" />
            最近编辑
          </div>

          <div v-if="papers.length === 0" class="px-2 py-3 text-sm text-muted-foreground text-center">
            还没有试卷
          </div>

          <button
            v-for="(paper, idx) in papers.slice(0, 3)"
            :key="paper.id"
            class="w-full flex items-center justify-between p-2 rounded hover:bg-accent transition-colors text-left group"
            @click="addToPaper(paper)"
          >
            <div class="flex-1 min-w-0">
              <div class="text-sm font-medium truncate">{{ paper.title }}</div>
              <div class="text-xs text-muted-foreground">{{ paper.question_count }} 题</div>
            </div>
            <kbd class="hidden group-hover:inline-flex h-5 px-1.5 items-center rounded border bg-muted text-xs font-mono">
              {{ idx + 1 }}
            </kbd>
          </button>
        </div>

        <div class="p-2 space-y-1">
          <button
            class="w-full flex items-center gap-2 p-2 rounded hover:bg-accent transition-colors text-sm"
            @click="createAndAdd"
          >
            <Plus class="h-4 w-4" />
            新建试卷并加入
          </button>
          <button
            v-if="total > 3"
            class="w-full flex items-center justify-between p-2 rounded hover:bg-accent transition-colors text-sm"
            @click="goToAllPapers"
          >
            <div class="flex items-center gap-2">
              <List class="h-4 w-4" />
              查看全部
            </div>
            <Badge variant="secondary">{{ total }}</Badge>
          </button>
        </div>
      </div>
    </PopoverContent>
  </Popover>
</template>
