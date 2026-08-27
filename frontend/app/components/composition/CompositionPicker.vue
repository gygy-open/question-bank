<script setup lang="ts">
import { ref, watch } from 'vue'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Search, Loader2 } from '@lucide/vue'
import { toast } from 'vue-sonner'
import { formatRelativeTime } from '@/lib/utils'
import { useCompositions } from '@/composables/useCompositions'
import type { Composition, CompositionDetail, CompositionScope } from '@/types'

const props = defineProps<{
  open: boolean
  subjectId: number | null
  // 排除当前正在编辑的稿件，避免把自己插入自己。
  excludeCompositionId?: number | null
  excludeScope?: CompositionScope | null
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  select: [detail: CompositionDetail]
}>()

const api = useCompositions()

const loading = ref(false)
const picking = ref(false)
const keyword = ref('')
const results = ref<Composition[]>([])
let seq = 0

function isExcluded(c: Composition): boolean {
  return c.id === props.excludeCompositionId && c.scope_type === props.excludeScope
}

async function search() {
  if (!props.subjectId) {
    results.value = []
    return
  }
  const mine = ++seq
  loading.value = true
  try {
    const kw = keyword.value || undefined
    const [personal, shared] = await Promise.all([
      api.listCompositions(props.subjectId, 'personal', { keyword: kw }),
      api.listCompositions(props.subjectId, 'shared', { keyword: kw }),
    ])
    if (mine !== seq) return
    results.value = [...personal, ...shared]
      .filter((c) => !isExcluded(c))
      .sort((a, b) => (a.updated_at < b.updated_at ? 1 : -1))
  } catch {
    if (mine === seq) results.value = []
  } finally {
    if (mine === seq) loading.value = false
  }
}

let debounce: ReturnType<typeof setTimeout> | null = null
watch(keyword, () => {
  if (debounce) clearTimeout(debounce)
  debounce = setTimeout(search, 250)
})

watch(
  () => props.open,
  (v) => {
    if (v) {
      keyword.value = ''
      results.value = []
      search()
    }
  },
)

async function pick(c: Composition) {
  if (!props.subjectId || picking.value) return
  picking.value = true
  try {
    const detail = await api.getComposition(props.subjectId, c.scope_type, c.id)
    emit('select', detail)
    emit('update:open', false)
  } catch {
    toast.error('加载稿件内容失败，请重试')
  } finally {
    picking.value = false
  }
}
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogContent class="max-w-2xl">
      <DialogHeader>
        <DialogTitle>插入稿件</DialogTitle>
        <DialogDescription>选择另一份稿件，将其全部内容克隆插入当前画布。</DialogDescription>
      </DialogHeader>

      <div class="relative">
        <Search class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input v-model="keyword" placeholder="搜索稿件标题…" class="pl-9" />
      </div>

      <div v-if="loading" class="flex h-[360px] items-center justify-center">
        <Loader2 class="h-6 w-6 animate-spin text-muted-foreground" />
      </div>

      <div
        v-else-if="results.length === 0"
        class="flex h-[360px] items-center justify-center text-sm text-muted-foreground"
      >
        没有匹配的稿件
      </div>

      <ScrollArea v-else class="h-[360px] pr-3">
        <div class="space-y-2">
          <button
            v-for="c in results"
            :key="`${c.scope_type}-${c.id}`"
            class="w-full rounded-lg border p-3 text-left transition-colors hover:border-primary hover:bg-muted/50 disabled:pointer-events-none disabled:opacity-50"
            :disabled="picking"
            @click="pick(c)"
          >
            <div class="mb-1 flex items-center gap-2">
              <Badge variant="secondary" class="text-xs">{{ c.scope_type === 'personal' ? '个人' : '共享' }}</Badge>
              <span class="text-xs text-muted-foreground">{{ formatRelativeTime(c.updated_at) }}</span>
            </div>
            <p class="line-clamp-1 text-sm font-medium">{{ c.title }}</p>
          </button>
        </div>
      </ScrollArea>
    </DialogContent>
  </Dialog>
</template>
