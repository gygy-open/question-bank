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
const groups = ref<Composition[]>([])
const searchQuery = ref('')
const selectedGroupId = ref<number | null>(null)

const filteredGroups = computed(() => {
  if (!searchQuery.value) return groups.value
  const q = searchQuery.value.toLowerCase()
  return groups.value.filter((p) => p.title.toLowerCase().includes(q))
})

const loadGroups = async () => {
  loading.value = true
  try {
    groups.value = await list({ comp_type: 'question_group', subject_id: currentSubjectId.value, sort: 'updated_desc' })
  } catch {
    toast.error('加载题组失败')
  } finally {
    loading.value = false
  }
}

watch(
  () => props.open,
  (v) => {
    if (v) {
      selectedGroupId.value = null
      searchQuery.value = ''
      loadGroups()
    }
  },
)

const confirmAdd = async () => {
  if (!selectedGroupId.value) return
  submitting.value = true
  try {
    const group = groups.value.find((p) => p.id === selectedGroupId.value)
    await appendQuestions(selectedGroupId.value, props.questionIds)
    toast.success(`已将 ${props.questionIds.length} 道题加入《${group?.title}》`)
    emit('added')
    emit('update:open', false)
  } catch {
    toast.error('加入失败')
  } finally {
    submitting.value = false
  }
}

const createNewGroup = async () => {
  submitting.value = true
  try {
    const group = await create({
      title: `新题组 ${new Date().toLocaleDateString()}`,
      comp_type: 'question_group',
      subject_id: currentSubjectId.value ?? null,
    })
    await appendQuestions(group.id, props.questionIds)
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
        <DialogTitle>选择题组</DialogTitle>
        <DialogDescription>
          将 {{ questionIds.length }} 道题加入题组
        </DialogDescription>
      </DialogHeader>

      <div class="relative">
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input v-model="searchQuery" placeholder="搜索题组标题..." class="pl-9" />
      </div>

      <div v-if="loading" class="h-[360px] flex items-center justify-center">
        <Loader2 class="h-6 w-6 animate-spin text-muted-foreground" />
      </div>

      <ScrollArea v-else class="h-[360px] pr-3">
        <div class="space-y-2">
          <button
            v-for="group in filteredGroups"
            :key="group.id"
            :class="[
              'w-full flex items-start gap-3 p-3 rounded-lg border-2 transition-all text-left',
              selectedGroupId === group.id ? 'border-primary bg-primary/5' : 'border-transparent bg-muted/40 hover:bg-muted',
            ]"
            @click="selectedGroupId = group.id"
          >
            <div class="flex-1 min-w-0">
              <div class="font-medium truncate">{{ group.title }}</div>
              <div class="text-xs text-muted-foreground mt-1 flex items-center gap-2">
                <Badge variant="secondary">{{ group.block_count }} 项</Badge>
                <span>{{ formatRelativeTime(group.updated_at) }}</span>
              </div>
            </div>
            <Check v-if="selectedGroupId === group.id" class="h-5 w-5 text-primary shrink-0" />
          </button>
          <div v-if="filteredGroups.length === 0" class="text-center text-sm text-muted-foreground py-8">
            暂无题组
          </div>
        </div>
      </ScrollArea>

      <DialogFooter class="gap-2 sm:justify-between">
        <Button variant="outline" :disabled="submitting" @click="createNewGroup">
          <Plus class="mr-2 h-4 w-4" /> 新建题组并加入
        </Button>
        <Button :disabled="!selectedGroupId || submitting" @click="confirmAdd">
          <Loader2 v-if="submitting" class="mr-2 h-4 w-4 animate-spin" />
          加入所选题组
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
