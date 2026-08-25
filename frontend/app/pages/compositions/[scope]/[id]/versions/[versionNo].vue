<script setup lang="ts">
// 组稿版本只读预览：加载 GET version detail，仅消费不可变 snapshot 渲染，绝不提供编辑入口。
import { ref, computed, onMounted, watch } from 'vue'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { ArrowLeft, Loader2, Users, Lock, AlertTriangle } from '@lucide/vue'
import { toast } from 'vue-sonner'
import SnapshotRenderer from '~/components/manager/composition/SnapshotRenderer.vue'
import { useCompositions } from '~/composables/useCompositions'
import { normalizeScope } from '~/lib/compositions'
import type { CompositionScope, CompositionVersionDetail } from '~/types'

const route = useRoute()
const router = useRouter()
const api = useCompositions()
const { currentSubjectId } = useSubjectContext()

const scope = computed<CompositionScope>(() => normalizeScope(route.params.scope))
const compositionId = computed(() => Number(route.params.id))
const versionNo = computed(() => Number(route.params.versionNo))

const version = ref<CompositionVersionDetail | null>(null)
const loading = ref(true)

const editorPath = computed(() => `/compositions/${scope.value}/${compositionId.value}`)

function formatTime(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

async function load() {
  if (!currentSubjectId.value) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    version.value = await api.getVersion(
      currentSubjectId.value,
      scope.value,
      compositionId.value,
      versionNo.value,
    )
  } catch {
    // 不存在/越权：退回编辑页并提示。
    toast.error('版本不存在或无权访问')
    router.push(editorPath.value)
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch([currentSubjectId, scope, compositionId, versionNo], load)

function backToEditor() {
  router.push(editorPath.value)
}
</script>

<template>
  <header class="flex h-16 shrink-0 items-center gap-2 border-b px-4">
    <Button variant="ghost" size="icon" class="h-8 w-8" @click="backToEditor">
      <ArrowLeft class="h-4 w-4" />
    </Button>
    <div class="min-w-0 flex-1">
      <p class="truncate text-sm font-medium">
        {{ version?.title || '版本预览' }}
      </p>
    </div>
    <Badge v-if="version" variant="outline" class="shrink-0 font-mono">v{{ version.version_no }}</Badge>
    <Badge variant="outline" class="gap-1">
      <component :is="scope === 'shared' ? Users : Lock" class="h-3 w-3" />
      {{ scope === 'shared' ? '共享' : '个人' }}
    </Badge>
  </header>

  <div class="flex flex-1 flex-col px-4 py-6">
    <div v-if="loading" class="flex justify-center py-16">
      <Loader2 class="h-6 w-6 animate-spin text-muted-foreground" />
    </div>

    <div v-else-if="version" class="mx-auto flex w-full max-w-4xl flex-col gap-6">
      <!-- 版本元信息（只读，无任何编辑入口） -->
      <div class="space-y-2">
        <div class="flex flex-wrap items-center gap-2">
          <h1 class="text-xl font-semibold">{{ version.title }}</h1>
          <Badge variant="secondary">只读版本</Badge>
        </div>
        <p v-if="version.label" class="text-sm text-muted-foreground">{{ version.label }}</p>
        <div class="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span>版本号 v{{ version.version_no }}</span>
          <span>定稿时间 {{ formatTime(version.finalized_at) }}</span>
          <span>源修订 r{{ version.source_revision }}</span>
          <span>定稿人 用户 #{{ version.finalized_by }}</span>
        </div>
      </div>

      <Separator />

      <SnapshotRenderer :snapshot="version.snapshot" />
    </div>

    <div v-else class="flex flex-col items-center gap-3 py-16 text-center text-sm text-muted-foreground">
      <AlertTriangle class="h-5 w-5 text-amber-500" />
      <span>无法加载此版本</span>
      <Button size="sm" variant="outline" @click="backToEditor">返回编辑页</Button>
    </div>
  </div>
</template>
