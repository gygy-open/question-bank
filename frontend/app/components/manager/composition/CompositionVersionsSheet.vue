<script setup lang="ts">
// 编辑页版本列表侧栏：懒加载（打开时拉取），仅展示摘要（不含 snapshot），点击进入只读预览。
import { ref, watch } from 'vue'
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription,
} from '@/components/ui/sheet'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Loader2, History, RefreshCw, ChevronRight, AlertTriangle } from '@lucide/vue'
import { useCompositions } from '~/composables/useCompositions'
import type { CompositionScope, CompositionVersionSummary } from '~/types'

const props = defineProps<{
  subjectId: number
  scope: CompositionScope
  compositionId: number
}>()

const open = defineModel<boolean>('open', { default: false })

const api = useCompositions()
const loading = ref(false)
const error = ref(false)
const versions = ref<CompositionVersionSummary[]>([])
const loaded = ref(false)

async function load() {
  loading.value = true
  error.value = false
  try {
    versions.value = await api.listVersions(props.subjectId, props.scope, props.compositionId)
    loaded.value = true
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}

// 打开即加载（含刷新最新定稿结果）。
watch(open, (isOpen) => {
  if (isOpen) load()
})

// 供外部在定稿成功后强制刷新。
defineExpose({ refresh: load })

function formatTime(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}
</script>

<template>
  <Sheet v-model:open="open">
    <SheetContent side="right" class="w-full sm:max-w-md">
      <SheetHeader>
        <SheetTitle class="flex items-center gap-2">
          <History class="h-4 w-4" /> 版本历史
        </SheetTitle>
        <SheetDescription>定稿后冻结的不可变版本，点击可打开只读预览。</SheetDescription>
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
          <span>加载版本列表失败</span>
          <Button size="sm" variant="outline" @click="load">
            <RefreshCw class="mr-2 h-4 w-4" /> 重试
          </Button>
        </div>

        <!-- 空态 -->
        <p
          v-else-if="loaded && versions.length === 0"
          class="py-12 text-center text-sm text-muted-foreground"
        >
          尚无定稿版本。使用「定稿」按钮冻结当前内容。
        </p>

        <!-- 列表（安静列表，非卡片墙） -->
        <ul v-else class="divide-y">
          <li v-for="v in versions" :key="v.id">
            <NuxtLink
              :to="`/compositions/${scope}/${compositionId}/versions/${v.version_no}`"
              class="flex items-center gap-3 py-3 transition-colors hover:bg-muted/50"
            >
              <Badge variant="outline" class="shrink-0 font-mono">v{{ v.version_no }}</Badge>
              <div class="min-w-0 flex-1">
                <p class="truncate text-sm font-medium">
                  {{ v.label || `版本 ${v.version_no}` }}
                </p>
                <p class="truncate text-xs text-muted-foreground">
                  {{ formatTime(v.finalized_at) }} · 源修订 r{{ v.source_revision }}
                </p>
              </div>
              <TooltipProvider :delay-duration="300">
                <Tooltip>
                  <TooltipTrigger as-child>
                    <span class="text-xs text-muted-foreground">用户 #{{ v.finalized_by }}</span>
                  </TooltipTrigger>
                  <TooltipContent>定稿人</TooltipContent>
                </Tooltip>
              </TooltipProvider>
              <ChevronRight class="h-4 w-4 shrink-0 text-muted-foreground" />
            </NuxtLink>
          </li>
        </ul>
      </div>
    </SheetContent>
  </Sheet>
</template>
