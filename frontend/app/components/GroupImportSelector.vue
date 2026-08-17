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
  /** 要解包导入的题组 id。 */
  groupId: number | null
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  imported: []
}>()

const { list, create, importGroup } = useCompositions()
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
  },
)

const confirmImport = async () => {
  if (!selectedPaperId.value || props.groupId == null) return
  submitting.value = true
  try {
    const paper = papers.value.find((p) => p.id === selectedPaperId.value)
    await importGroup(selectedPaperId.value, props.groupId)
    toast.success(`已解包加入《${paper?.title}》`)
    emit('imported')
    emit('update:open', false)
  } catch {
    toast.error('加入失败')
  } finally {
    submitting.value = false
  }
}

const createAndImport = async () => {
  if (props.groupId == null) return
  submitting.value = true
  try {
    const paper = await create({
      title: `新试卷 ${new Date().toLocaleDateString()}`,
      comp_type: 'exam_paper',
      subject_id: currentSubjectId.value ?? null,
    })
    await importGroup(paper.id, props.groupId)
    toast.success('已创建并解包加入')
    emit('imported')
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
        <DialogTitle>加入试题篮</DialogTitle>
        <DialogDescription>
          将题组内容解包，追加到所选试卷末尾
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
              selectedPaperId === paper.id ? 'border-primary bg-primary/5' : 'border-transparent bg-muted/40 hover:bg-muted',
            ]"
            @click="selectedPaperId = paper.id"
          >
            <div class="flex-1 min-w-0">
              <div class="font-medium truncate">{{ paper.title }}</div>
              <div class="text-xs text-muted-foreground mt-1 flex items-center gap-2">
                <Badge variant="secondary">{{ paper.block_count }} 项</Badge>
                <span>{{ formatRelativeTime(paper.updated_at) }}</span>
              </div>
            </div>
            <Check v-if="selectedPaperId === paper.id" class="h-5 w-5 text-primary shrink-0" />
          </button>
          <div v-if="filteredPapers.length === 0" class="text-center text-sm text-muted-foreground py-8">
            暂无试卷
          </div>
        </div>
      </ScrollArea>

      <DialogFooter class="gap-2 sm:justify-between">
        <Button variant="outline" :disabled="submitting" @click="createAndImport">
          <Plus class="mr-2 h-4 w-4" /> 新建试卷并加入
        </Button>
        <Button :disabled="!selectedPaperId || submitting" @click="confirmImport">
          <Loader2 v-if="submitting" class="mr-2 h-4 w-4 animate-spin" />
          加入所选试卷
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
