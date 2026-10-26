<script setup lang="ts">
import { formatDateTime } from '@/lib/locale'
// 编辑页时间线侧栏：懒加载（打开时拉取第一页），游标分页「加载更多」，只读展示。
import { computed, ref, watch } from 'vue'
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription,
} from '@/components/ui/sheet'
import { Button } from '@/components/ui/button'
import {
  Loader2, Clock, RefreshCw, AlertTriangle,
  FilePlus, Pencil, FolderInput, Trash2, RotateCcw, Save, CheckCircle2, Image as ImageIcon,
} from '@lucide/vue'
import { useCompositions } from '~/composables/useCompositions'
import type { CompositionEvent, CompositionEventType, CompositionScope } from '~/types'

const props = defineProps<{
  subjectId: number
  scope: CompositionScope
  compositionId: number
}>()

const open = defineModel<boolean>('open', { default: false })

const { t } = useI18n()
const api = useCompositions()
const loading = ref(false)
const loadingMore = ref(false)
const error = ref(false)
const loaded = ref(false)
const hasMore = ref(false)
const events = ref<CompositionEvent[]>([])

// event_type → 中文标签 + 图标；后端 summary 作为补充细节一并展示。
const EVENT_META: Record<CompositionEventType, { labelKey: string; icon: unknown }> = {
  created: { labelKey: 'compositionVersions.events.created', icon: FilePlus },
  updated: { labelKey: 'compositionVersions.events.updated', icon: Pencil },
  moved: { labelKey: 'compositionVersions.events.moved', icon: FolderInput },
  deleted: { labelKey: 'compositionVersions.events.deleted', icon: Trash2 },
  restored: { labelKey: 'compositionVersions.events.restored', icon: RotateCcw },
  nodes_replaced: { labelKey: 'compositionVersions.events.nodesReplaced', icon: Save },
  question_nodes_synced: { labelKey: 'compositionVersions.events.questionNodesSynced', icon: RefreshCw },
  finalized: { labelKey: 'compositionVersions.events.finalized', icon: CheckCircle2 },
  media_replaced: { labelKey: 'compositionVersions.events.mediaReplaced', icon: ImageIcon },
}

function metaFor(type: CompositionEventType) {
  const meta = EVENT_META[type]
  return meta ? { label: t(meta.labelKey), icon: meta.icon } : { label: type, icon: Clock }
}

function actorLabel(e: CompositionEvent): string {
  return e.actor?.full_name || e.actor?.username || t('compositionVersions.userFallback', { id: e.actor_id })
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : formatDateTime(d)
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
          <Clock class="h-4 w-4" /> {{ t('compositionEditor.timeline') }}
        </SheetTitle>
        <SheetDescription>{{ t('compositionVersions.timeline.description') }}</SheetDescription>
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
          <span>{{ t('compositionVersions.timeline.loadFailed') }}</span>
          <Button size="sm" variant="outline" @click="load">
            <RefreshCw class="mr-2 h-4 w-4" /> {{ t('common.retry') }}
          </Button>
        </div>

        <!-- 空态 -->
        <p v-else-if="isEmpty" class="py-12 text-center text-sm text-muted-foreground">
          {{ t('compositionVersions.timeline.empty') }}
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
              {{ t('common.loadMore') }}
            </Button>
          </div>
        </template>
      </div>
    </SheetContent>
  </Sheet>
</template>
