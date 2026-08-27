<script setup lang="ts">
// 编辑页时间线侧栏：懒加载（打开时拉取第一页），游标分页「加载更多」，只读展示。
import { computed, ref, watch } from 'vue'
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription,
} from '@/components/ui/sheet'
import { Button } from '@/components/ui/button'
import {
  Loader2, Clock, RefreshCw, AlertTriangle,
  FilePlus, Pencil, FolderInput, Trash2, RotateCcw, Save, CheckCircle2,
} from '@lucide/vue'
import { useCompositions } from '~/composables/useCompositions'
import type { CompositionEvent, CompositionEventType, CompositionScope } from '~/types'

const props = defineProps<{
  subjectId: number
  scope: CompositionScope
  compositionId: number
}>()

const open = defineModel<boolean>('open', { default: false })

const api = useCompositions()
const loading = ref(false)
const loadingMore = ref(false)
const error = ref(false)
const loaded = ref(false)
const hasMore = ref(false)
const events = ref<CompositionEvent[]>([])

// event_type → 中文标签 + 图标；后端 summary 作为补充细节一并展示。
const EVENT_META: Record<CompositionEventType, { label: string; icon: unknown }> = {
  created: { label: '创建组稿', icon: FilePlus },
  updated: { label: '更新元数据', icon: Pencil },
  moved: { label: '移动目录', icon: FolderInput },
  deleted: { label: '删除组稿', icon: Trash2 },
  restored: { label: '恢复组稿', icon: RotateCcw },
  nodes_replaced: { label: '保存内容', icon: Save },
  question_nodes_synced: { label: '同步题目', icon: RefreshCw },
  finalized: { label: '定稿', icon: CheckCircle2 },
}

function metaFor(type: CompositionEventType) {
  return EVENT_META[type] ?? { label: type, icon: Clock }
}

function actorLabel(e: CompositionEvent): string {
  return e.actor?.full_name || e.actor?.username || `用户 #${e.actor_id}`
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

async function load() {
  loading.value = true
  error.value = false
  try {
    const page = await api.listEvents(props.subjectId, props.scope, props.compositionId)
    events.value = page.items
    hasMore.value = page.has_more
    loaded.value = true
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}

async function loadMore() {
  const lastId = events.value.at(-1)?.id
  if (lastId == null || loadingMore.value) return
  loadingMore.value = true
  try {
    const page = await api.listEvents(props.subjectId, props.scope, props.compositionId, { beforeId: lastId })
    events.value = [...events.value, ...page.items]
    hasMore.value = page.has_more
  } catch {
    // 加载更多失败：静默保留已加载内容，用户可再次点击重试。
  } finally {
    loadingMore.value = false
  }
}

// 打开即加载（含刷新最新事件）。
watch(open, (isOpen) => {
  if (isOpen) load()
})

const isEmpty = computed(() => loaded.value && events.value.length === 0)
</script>

<template>
  <Sheet v-model:open="open">
    <SheetContent side="right" class="w-full sm:max-w-md">
      <SheetHeader>
        <SheetTitle class="flex items-center gap-2">
          <Clock class="h-4 w-4" /> 时间线
        </SheetTitle>
        <SheetDescription>谁在什么时候对这份组稿做了什么，按时间倒序排列。</SheetDescription>
      </SheetHeader>

      <div class="flex-1 overflow-y-auto px-4 pb-4">
        <!-- 加载态 -->
        <div v-if="loading" class="flex justify-center py-16">
          <Loader2 class="h-5 w-5 animate-spin text-muted-foreground" />
        </div>

        <!-- 错误态 -->
        <div
          v-else-if="error"
          class="flex flex-col items-center gap-3 py-12 text-center text-sm text-muted-foreground"
        >
          <AlertTriangle class="h-5 w-5 text-amber-500" />
          <span>加载时间线失败</span>
          <Button size="sm" variant="outline" @click="load">
            <RefreshCw class="mr-2 h-4 w-4" /> 重试
          </Button>
        </div>

        <!-- 空态 -->
        <p v-else-if="isEmpty" class="py-12 text-center text-sm text-muted-foreground">
          暂无事件记录。
        </p>

        <!-- 列表 -->
        <template v-else>
          <ul class="divide-y">
            <li v-for="e in events" :key="e.id" class="flex items-start gap-3 py-3">
              <component :is="metaFor(e.event_type).icon" class="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
              <div class="min-w-0 flex-1">
                <p class="truncate text-sm font-medium">{{ metaFor(e.event_type).label }}</p>
                <p class="truncate text-xs text-muted-foreground">{{ e.summary }}</p>
                <p class="truncate text-xs text-muted-foreground">
                  {{ actorLabel(e) }} · {{ formatTime(e.created_at) }}
                </p>
              </div>
            </li>
          </ul>

          <div v-if="hasMore" class="flex justify-center pt-2">
            <Button size="sm" variant="outline" :disabled="loadingMore" @click="loadMore">
              <Loader2 v-if="loadingMore" class="mr-2 h-4 w-4 animate-spin" />
              加载更多
            </Button>
          </div>
        </template>
      </div>
    </SheetContent>
  </Sheet>
</template>
