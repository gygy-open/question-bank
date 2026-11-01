<script setup lang="ts">
import { computed, onActivated, onDeactivated, onUnmounted, ref, watch } from 'vue'
import {
  AlertTriangle,
  FileArchive,
  FileCode,
  FileText,
  Image as ImageIcon,
  Loader2,
  MoreHorizontal,
  Plus,
  RotateCcw,
  Upload,
} from '@lucide/vue'
import { toast } from 'vue-sonner'
import PageHeader from '@/components/PageHeader.vue'
import NewImportDialog from '@/components/import/NewImportDialog.vue'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { formatRelativeTime } from '@/lib/utils'
import { getApiErrorDetail } from '@/lib/apiErrors'
import { groupTasks, statusLine, type ImportGroup } from '@/lib/importTasks'
import type { ImportPauseReason, ImportTaskItem } from '@/composables/useImportQueue'

definePageMeta({ layout: 'default' })

const { t } = useI18n()
const { $api } = useNuxtApp()
const route = useRoute()
const router = useRouter()
const { user } = useAuth()
const queue = useImportQueue()
const { tasks, summary, ownerFilter, hasMore, hasActive } = queue

const isSuperuser = computed(() => !!user.value?.is_superuser)
const selectedId = computed(() => (route.params.id ? Number(route.params.id) : null))
const groups = computed(() => groupTasks(tasks.value))

// --- 新建导入 ---
const newOpen = ref(false)
const pendingFiles = ref<File[]>([])
const pendingText = ref('')
const openNew = (files: File[] = [], text = '') => {
  pendingFiles.value = files
  pendingText.value = text
  newOpen.value = true
}
const onCreated = async (items: ImportTaskItem[]) => {
  await queue.refresh()
  if (items.length === 1 && items[0]) router.push(`/imports/${items[0].id}`)
}

// 整页拖入文件即可导入。
const dragDepth = ref(0)
const hasFiles = (e: DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes('Files')
const onDragEnter = (e: DragEvent) => {
  if (!hasFiles(e) || newOpen.value) return
  dragDepth.value++
}
const onDragLeave = (e: DragEvent) => {
  if (!hasFiles(e) || newOpen.value) return
  dragDepth.value = Math.max(0, dragDepth.value - 1)
}
const onDrop = (e: DragEvent) => {
  dragDepth.value = 0
  if (newOpen.value) return
  const files = Array.from(e.dataTransfer?.files ?? [])
  if (files.length) openNew(files)
}

// 页面上直接 ⌘V / Ctrl+V 粘贴截图或文本(输入框内的粘贴不拦截)。
const isEditable = (el: EventTarget | null) => {
  const node = el as HTMLElement | null
  return !!node && (node.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(node.tagName))
}
const onPaste = (e: ClipboardEvent) => {
  if (newOpen.value || isEditable(e.target) || isEditable(document.activeElement)) return
  const items = Array.from(e.clipboardData?.items ?? [])
  const images = items
    .filter((item) => item.type.startsWith('image/'))
    .map((item) => item.getAsFile())
    .filter((file): file is File => !!file)
    .map((blob, i) => new File([blob], `pasted-image-${Date.now()}-${i}.png`, { type: blob.type }))
  if (images.length) {
    e.preventDefault()
    openNew(images)
    return
  }
  const text = e.clipboardData?.getData('text/plain') ?? ''
  if (text.trim()) {
    e.preventDefault()
    openNew([], text)
  }
}

// --- 暂停提示 ---
const PAUSE_PRIORITY: ImportPauseReason[] = ['auth', 'model', 'quota', 'unavailable']
const pausedReason = computed(() => PAUSE_PRIORITY.find((reason) => summary.value?.paused_reasons?.[reason]) ?? null)
const pausedCount = computed(() => summary.value?.counts.paused ?? 0)
const resuming = ref(false)
const resumeAll = async () => {
  resuming.value = true
  try {
    const res = await $api<{ count: number }>('/imports/resume', { method: 'POST', body: {} })
    toast.success(t('imports.paused.resumed', { count: res.count }))
    await queue.refresh()
  } catch (e: any) {
    toast.error(getApiErrorDetail(e, e.message))
  } finally {
    resuming.value = false
  }
}

// --- 管理员 ---
interface UserOption { id: number; full_name?: string | null; username: string }
const users = ref<UserOption[]>([])
watch(isSuperuser, async (admin) => {
  if (!admin) return
  try {
    users.value = await $api<UserOption[]>('/users', { query: { limit: 100 } })
  } catch {
    users.value = []
  }
}, { immediate: true })
const ownerValue = computed({
  get: () => (ownerFilter.value === null ? 'mine' : String(ownerFilter.value)),
  set: (value: string) => {
    ownerFilter.value = value === 'mine' ? null : value === 'all' ? 'all' : Number(value)
  },
})
watch(ownerFilter, () => queue.refresh())

const resetStuck = async () => {
  if (!confirm(t('imports.menu.resetStuckConfirm'))) return
  try {
    const data = await $api<{ count: number }>('/imports/reset-stuck', { method: 'POST' })
    toast.success(t('imports.menu.resetDone', { count: data.count }))
    await queue.refresh()
  } catch {
    toast.error(t('imports.menu.resetFailed'))
  }
}

// --- 轮询:有进行中的导入时 3 秒刷新一次,否则 15 秒 ---
let timer: ReturnType<typeof setInterval> | null = null
let ticks = 0
const stopPolling = () => {
  if (timer) clearInterval(timer)
  timer = null
}
const startPolling = () => {
  stopPolling()
  timer = setInterval(() => {
    ticks++
    if (hasActive.value || ticks % 5 === 0) queue.refresh()
  }, 3000)
}

onActivated(() => {
  queue.refresh()
  startPolling()
  window.addEventListener('paste', onPaste)
})
watch(() => route.query.new, (value) => {
  if (!value) return
  openNew()
  router.replace({ query: { ...route.query, new: undefined } })
}, { immediate: true })
onDeactivated(() => {
  stopPolling()
  window.removeEventListener('paste', onPaste)
})
onUnmounted(() => {
  stopPolling()
  window.removeEventListener('paste', onPaste)
})

const fileIcon = (task: ImportTaskItem) => {
  switch (task.file_type) {
    case 'image': return ImageIcon
    case 'archive': return FileArchive
    case 'docx': return FileText
    default: return FileCode
  }
}

const lineClass: Record<ImportGroup, string> = {
  review: 'text-primary',
  active: 'text-muted-foreground',
  paused: 'text-amber-600 dark:text-amber-400',
  failed: 'text-destructive',
  history: 'text-muted-foreground',
}
</script>

<template>
  <PageHeader :title="t('imports.title')">
    <template #actions>
      <Button size="sm" @click="openNew()">
        <Plus class="mr-1.5 h-4 w-4" />{{ t('imports.new') }}
      </Button>
      <DropdownMenu v-if="isSuperuser">
        <DropdownMenuTrigger as-child>
          <Button variant="ghost" size="icon" class="h-8 w-8" :title="t('imports.menu.more')">
            <MoreHorizontal class="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" class="w-56">
          <DropdownMenuLabel>{{ t('imports.menu.show') }}</DropdownMenuLabel>
          <DropdownMenuRadioGroup v-model="ownerValue">
            <DropdownMenuRadioItem value="mine">{{ t('imports.menu.mine') }}</DropdownMenuRadioItem>
            <DropdownMenuRadioItem value="all">{{ t('imports.menu.allUsers') }}</DropdownMenuRadioItem>
            <DropdownMenuRadioItem v-for="u in users.filter((u) => u.id !== user?.id)" :key="u.id" :value="String(u.id)">
              {{ u.full_name || u.username }}
            </DropdownMenuRadioItem>
          </DropdownMenuRadioGroup>
          <DropdownMenuSeparator />
          <DropdownMenuItem @click="resetStuck">
            <RotateCcw class="mr-2 h-4 w-4" />{{ t('imports.menu.resetStuck') }}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </template>
  </PageHeader>

  <div
    class="relative grid flex-1 md:grid-cols-[19rem_minmax(0,1fr)]"
    @dragenter.prevent="onDragEnter"
    @dragover.prevent
    @dragleave.prevent="onDragLeave"
    @drop.prevent="onDrop"
  >
    <aside
      class="border-r md:sticky md:top-0 md:h-[calc(100svh-4rem)] md:overflow-y-auto"
      :class="selectedId ? 'hidden md:block' : ''"
    >
      <div v-if="pausedReason" class="m-3 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
        <div class="flex gap-2">
          <AlertTriangle class="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
          <p>{{ t(`imports.paused.${pausedReason}`, { count: pausedCount }) }}</p>
        </div>
        <div class="mt-2 flex flex-wrap justify-end gap-2">
          <Button v-if="pausedReason === 'auth' || pausedReason === 'model'" size="sm" variant="outline" as-child>
            <NuxtLink to="/settings">{{ t('imports.paused.openSettings') }}</NuxtLink>
          </Button>
          <Button size="sm" variant="outline" :disabled="resuming" @click="resumeAll">
            <Loader2 v-if="resuming" class="mr-1.5 h-3.5 w-3.5 animate-spin" />
            {{ pausedReason === 'unavailable' ? t('imports.paused.retryNow') : t('imports.paused.resumeAll') }}
          </Button>
        </div>
      </div>

      <div v-if="queue.loaded.value && !tasks.length" class="px-6 py-12 text-center text-sm text-muted-foreground">
        {{ t('imports.empty.list') }}
      </div>

      <nav v-for="section in groups" :key="section.group" class="py-2">
        <h3 class="px-4 pb-1 text-xs font-medium text-muted-foreground">
          {{ t(`imports.groups.${section.group}`) }}
          <span class="ml-1 tabular-nums">{{ section.tasks.length }}</span>
        </h3>
        <ul>
          <li v-for="task in section.tasks" :key="task.id">
            <NuxtLink
              :to="`/imports/${task.id}`"
              class="mx-2 flex items-start gap-3 rounded-md px-2 py-2 hover:bg-accent"
              :class="selectedId === task.id ? 'bg-accent' : ''"
            >
              <span class="relative mt-0.5 shrink-0">
                <component :is="fileIcon(task)" class="h-4 w-4 text-muted-foreground" />
                <span v-if="task.status === 'review_ready'" class="absolute -right-1 -top-1 h-2 w-2 rounded-full bg-primary" />
              </span>
              <span class="min-w-0 flex-1">
                <span class="block truncate text-sm font-medium" :title="task.original_filename">{{ task.original_filename }}</span>
                <span class="flex items-center gap-1 text-xs" :class="lineClass[section.group]">
                  <Loader2 v-if="task.status === 'processing'" class="h-3 w-3 shrink-0 animate-spin" />
                  <span class="truncate">{{ t(statusLine(task).key, statusLine(task).params ?? {}) }}</span>
                </span>
                <span class="block truncate text-xs text-muted-foreground">
                  {{ formatRelativeTime(task.updated_at || task.created_at) }}<template v-if="ownerFilter !== null && task.owner_name"> · {{ task.owner_name }}</template>
                </span>
              </span>
            </NuxtLink>
          </li>
        </ul>
      </nav>

      <div v-if="hasMore" class="p-3">
        <Button variant="ghost" size="sm" class="w-full" @click="queue.loadMore()">{{ t('imports.loadMore') }}</Button>
      </div>
    </aside>

    <section class="min-w-0" :class="selectedId ? '' : 'hidden md:block'">
      <NuxtPage />
    </section>

    <div
      v-if="dragDepth > 0"
      class="pointer-events-none absolute inset-0 z-30 m-3 flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed border-primary bg-background/90"
    >
      <Upload class="h-8 w-8 text-primary" />
      <p class="text-base font-medium">{{ t('imports.dropHint') }}</p>
    </div>
  </div>

  <NewImportDialog
    v-model:open="newOpen"
    :initial-files="pendingFiles"
    :initial-text="pendingText"
    @created="onCreated"
  />
</template>
