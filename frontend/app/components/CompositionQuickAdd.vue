<script setup lang="ts">
import { ref } from 'vue'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { FilePlus, Clock, Plus, Loader2 } from '@lucide/vue'
import { toast } from 'vue-sonner'
import { useCompositions, CompositionConflictError } from '@/composables/useCompositions'
import { useAddQuestionsToComposition } from '@/composables/useAddQuestionsToComposition'
import type { Composition } from '~/types'

const props = defineProps<{
  questionId: number
  subjectId: number | null
}>()

const { listCompositions, createComposition } = useCompositions()
const { addQuestionsToComposition } = useAddQuestionsToComposition()

const open = ref(false)
const loading = ref(false)
const adding = ref(false)
const compositions = ref<Composition[]>([])

const loadCompositions = async () => {
  if (!props.subjectId) return
  loading.value = true
  try {
    const [personal, shared] = await Promise.all([
      listCompositions(props.subjectId, 'personal'),
      listCompositions(props.subjectId, 'shared'),
    ])
    compositions.value = [...personal, ...shared]
      .sort((a, b) => (a.updated_at < b.updated_at ? 1 : -1))
      .slice(0, 3)
  } catch {
    toast.error('加载稿件失败')
  } finally {
    loading.value = false
  }
}

const onOpenChange = (value: boolean) => {
  open.value = value
  if (value) loadCompositions()
}

const handleConflict = (err: unknown) => {
  if (err instanceof CompositionConflictError && err.kind === 'revision') {
    toast.error('稿件已被他人更新，请重新打开再试一次')
  } else {
    toast.error('加入稿件失败')
  }
}

// 加入成功后在 toast 里附上快捷跳转，无需再去组稿工作台里找该稿件。
const jumpAction = (scope: Composition['scope_type'], id: number) => ({
  action: {
    label: '前往查看',
    onClick: () => navigateTo(`/compositions/${scope}/${id}`),
  },
})

const addToComposition = async (composition: Composition) => {
  if (!props.subjectId || adding.value) return
  adding.value = true
  try {
    await addQuestionsToComposition(props.subjectId, composition.scope_type, composition.id, [props.questionId])
    toast.success(`已加入《${composition.title}》`, jumpAction(composition.scope_type, composition.id))
    open.value = false
  } catch (err) {
    handleConflict(err)
  } finally {
    adding.value = false
  }
}

const createAndAdd = async () => {
  if (!props.subjectId || adding.value) return
  adding.value = true
  try {
    const composition = await createComposition(props.subjectId, 'personal', {
      title: `新稿件 ${new Date().toLocaleDateString()}`,
    })
    await addQuestionsToComposition(props.subjectId, 'personal', composition.id, [props.questionId])
    toast.success(`已创建并加入《${composition.title}》`, jumpAction('personal', composition.id))
    open.value = false
  } catch (err) {
    handleConflict(err)
  } finally {
    adding.value = false
  }
}

const goToWorkspace = () => {
  open.value = false
  navigateTo('/compositions/personal')
}

const onKey = (e: KeyboardEvent) => {
  const idx = ['1', '2', '3'].indexOf(e.key)
  if (idx >= 0 && compositions.value[idx]) {
    e.preventDefault()
    addToComposition(compositions.value[idx])
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
        title="加入稿件"
      >
        <FilePlus class="h-4 w-4" />
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

          <div v-if="compositions.length === 0" class="px-2 py-3 text-sm text-muted-foreground text-center">
            还没有稿件
          </div>

          <button
            v-for="(composition, idx) in compositions"
            :key="`${composition.scope_type}-${composition.id}`"
            class="w-full flex items-center justify-between p-2 rounded hover:bg-accent transition-colors text-left group"
            :disabled="adding"
            @click="addToComposition(composition)"
          >
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-1.5">
                <span class="text-sm font-medium truncate">{{ composition.title }}</span>
                <Badge variant="secondary" class="text-[10px] px-1">{{ composition.scope_type === 'personal' ? '个人' : '共享' }}</Badge>
              </div>
            </div>
            <kbd class="hidden group-hover:inline-flex h-5 px-1.5 items-center rounded border bg-muted text-xs font-mono">
              {{ idx + 1 }}
            </kbd>
          </button>
        </div>

        <div class="p-2 space-y-1">
          <button
            class="w-full flex items-center gap-2 p-2 rounded hover:bg-accent transition-colors text-sm"
            :disabled="adding"
            @click="createAndAdd"
          >
            <Plus class="h-4 w-4" />
            新建稿件并加入
          </button>
          <button
            class="w-full flex items-center justify-between p-2 rounded hover:bg-accent transition-colors text-sm"
            @click="goToWorkspace"
          >
            <span>前往组稿工作台</span>
          </button>
        </div>
      </div>
    </PopoverContent>
  </Popover>
</template>
