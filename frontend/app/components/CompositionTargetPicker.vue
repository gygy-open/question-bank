<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Search, Check, Plus, Loader2 } from '@lucide/vue'
import { toast } from 'vue-sonner'
import { useCompositions, CompositionConflictError } from '@/composables/useCompositions'
import { useAddQuestionsToComposition } from '@/composables/useAddQuestionsToComposition'
import { formatRelativeTime } from '@/lib/utils'
import type { Composition, CompositionScope } from '~/types'

const props = defineProps<{
  open: boolean
  subjectId: number | null
  questionIds: number[]
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  added: []
}>()

const { listCompositions, createComposition } = useCompositions()
const { addQuestionsToComposition } = useAddQuestionsToComposition()

const loading = ref(false)
const submitting = ref(false)
const compositions = ref<Composition[]>([])
const searchQuery = ref('')
const selected = ref<Composition | null>(null)

const filteredCompositions = computed(() => {
  if (!searchQuery.value) return compositions.value
  const q = searchQuery.value.toLowerCase()
  return compositions.value.filter((c) => c.title.toLowerCase().includes(q))
})

const loadCompositions = async () => {
  if (!props.subjectId) return
  loading.value = true
  try {
    const [personal, shared] = await Promise.all([
      listCompositions(props.subjectId, 'personal'),
      listCompositions(props.subjectId, 'shared'),
    ])
    compositions.value = [...personal, ...shared].sort((a, b) => (a.updated_at < b.updated_at ? 1 : -1))
  } catch {
    toast.error('加载稿件失败')
  } finally {
    loading.value = false
  }
}

watch(
  () => props.open,
  (v) => {
    if (v) {
      selected.value = null
      searchQuery.value = ''
      loadCompositions()
    }
  },
)

const handleConflict = (err: unknown) => {
  if (err instanceof CompositionConflictError && err.kind === 'revision') {
    toast.error('稿件已被他人更新，请重新打开选择器再试一次')
  } else {
    toast.error('加入稿件失败')
  }
}

// 加入成功后在 toast 里附上快捷跳转，无需再去组稿工作台里找该稿件。
interface JumpTarget {
  scope: CompositionScope
  id: number
}
const jumpAction = (target: JumpTarget) => ({
  action: {
    label: '前往查看',
    onClick: () => navigateTo(`/compositions/${target.scope}/${target.id}`),
  },
})

const confirmAdd = async () => {
  if (!selected.value || !props.subjectId) return
  submitting.value = true
  try {
    const result = await addQuestionsToComposition(
      props.subjectId,
      selected.value.scope_type,
      selected.value.id,
      props.questionIds,
    )
    toast.success(`已将 ${result.addedCount} 道题加入《${result.compositionTitle}》`, jumpAction({
      scope: selected.value.scope_type,
      id: selected.value.id,
    }))
    emit('added')
    emit('update:open', false)
  } catch (err) {
    handleConflict(err)
  } finally {
    submitting.value = false
  }
}

const createAndAdd = async () => {
  if (!props.subjectId) return
  submitting.value = true
  try {
    const composition = await createComposition(props.subjectId, 'personal', {
      title: `新稿件 ${new Date().toLocaleDateString()}`,
    })
    const result = await addQuestionsToComposition(
      props.subjectId,
      'personal',
      composition.id,
      props.questionIds,
    )
    toast.success(`已创建并加入 ${result.addedCount} 道题`, jumpAction({ scope: 'personal', id: composition.id }))
    emit('added')
    emit('update:open', false)
  } catch (err) {
    handleConflict(err)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogContent class="max-w-2xl">
      <DialogHeader>
        <DialogTitle>选择稿件</DialogTitle>
        <DialogDescription>
          将 {{ questionIds.length }} 道题加入稿件
        </DialogDescription>
      </DialogHeader>

      <div class="relative">
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input v-model="searchQuery" placeholder="搜索稿件标题..." class="pl-9" />
      </div>

      <div v-if="loading" class="h-[360px] flex items-center justify-center">
        <Loader2 class="h-6 w-6 animate-spin text-muted-foreground" />
      </div>

      <ScrollArea v-else class="h-[360px] pr-3">
        <div class="space-y-2">
          <button
            v-for="composition in filteredCompositions"
            :key="`${composition.scope_type}-${composition.id}`"
            :class="[
              'w-full flex items-start gap-3 p-3 rounded-lg border-2 transition-all text-left',
              selected?.id === composition.id && selected?.scope_type === composition.scope_type
                ? 'border-primary bg-primary/5'
                : 'border-transparent hover:border-muted hover:bg-muted/50',
            ]"
            @click="selected = composition"
          >
            <div class="flex-shrink-0 mt-1">
              <div
                :class="[
                  'w-5 h-5 rounded-full border-2 flex items-center justify-center transition-colors',
                  selected?.id === composition.id && selected?.scope_type === composition.scope_type
                    ? 'border-primary bg-primary'
                    : 'border-muted-foreground',
                ]"
              >
                <Check
                  v-if="selected?.id === composition.id && selected?.scope_type === composition.scope_type"
                  class="h-3 w-3 text-primary-foreground"
                />
              </div>
            </div>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <span class="text-sm font-medium truncate">{{ composition.title }}</span>
                <Badge variant="secondary" class="text-xs">{{ composition.scope_type === 'personal' ? '个人' : '共享' }}</Badge>
              </div>
              <div class="text-xs text-muted-foreground mt-0.5">{{ formatRelativeTime(composition.updated_at) }}</div>
            </div>
          </button>

          <div v-if="filteredCompositions.length === 0" class="py-8 text-center text-sm text-muted-foreground">
            还没有稿件
          </div>
        </div>
      </ScrollArea>

      <div class="flex items-center justify-between pt-2 border-t">
        <Button variant="ghost" size="sm" :disabled="submitting" @click="createAndAdd">
          <Plus class="mr-1 h-4 w-4" />
          新建稿件并加入
        </Button>
        <Button :disabled="!selected || submitting" @click="confirmAdd">
          <Loader2 v-if="submitting" class="mr-2 h-4 w-4 animate-spin" />
          加入所选稿件
        </Button>
      </div>
    </DialogContent>
  </Dialog>
</template>
