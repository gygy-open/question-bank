<script setup lang="ts">
import { ref, computed, watch, onActivated } from 'vue'
import PageHeader from '~/components/PageHeader.vue'
import CompositionFolderTree from '~/components/manager/CompositionFolderTree.vue'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import {
  Plus, FolderPlus, MoreVertical, Pencil, FolderInput, Trash2, ArchiveRestore,
  Archive, FileText, Clock, Loader2, Trash, RotateCcw, Users, Lock, Home, Copy,
} from '@lucide/vue'
import { toast } from 'vue-sonner'
import { useCompositions, CompositionConflictError } from '~/composables/useCompositions'
import {
  buildFolderTree, folderBreadcrumb, collectDescendantIds, normalizeScope,
} from '~/lib/compositions'
import { formatRelativeTime } from '@/lib/utils'
import type {
  Composition, CompositionFolder, CompositionFolderNode, CompositionScope,
} from '~/types'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const api = useCompositions()
const { currentSubject, currentSubjectId, hasSubjects } = useSubjectContext()

const scope = computed<CompositionScope>(() => normalizeScope(route.params.scope))

const folders = ref<CompositionFolder[]>([])
const compositions = ref<Composition[]>([])
const trashed = ref<Composition[]>([])
const loadingFolders = ref(false)
const loadingList = ref(false)
// 选中文件夹与 URL 的 ?folder= 查询参数双向绑定：地址栏编辑、浏览器前进后退、
// 详情页面包屑跳转都会生效，selectFolder 只负责改路由，具体加载由下方 watch 驱动。
const selectedFolderId = computed<number | null>(() => {
  const raw = route.query.folder
  const value = Array.isArray(raw) ? raw[0] : raw
  const n = Number(value)
  return value != null && Number.isFinite(n) ? n : null
})
const expanded = ref<Set<number>>(new Set())
const view = ref<'active' | 'trash'>('active')

const folderTree = computed(() => buildFolderTree(folders.value))
const breadcrumb = computed(() => folderBreadcrumb(folders.value, selectedFolderId.value))

const scopeHint = computed(() =>
  scope.value === 'shared'
    ? t('compositions.scopeHint.shared')
    : t('compositions.scopeHint.personal'),
)

// 扁平化目录为带缩进标签的选项，供“移动”选择器使用。
const flatFolderOptions = computed(() => {
  const out: { id: number; label: string }[] = []
  const walk = (nodes: CompositionFolderNode[], depth: number) => {
    for (const n of nodes) {
      out.push({ id: n.id, label: `${'\u00A0\u00A0'.repeat(depth)}${n.name}` })
      walk(n.children, depth + 1)
    }
  }
  walk(folderTree.value, 0)
  return out
})

function handleConflict(err: unknown, fallback: string) {
  if (err instanceof CompositionConflictError) {
    if (err.kind === 'revision') {
      toast.error(t('compositions.conflict.revision'))
    } else if (err.kind === 'folder-not-empty') {
      toast.error(t('compositions.conflict.folderNotEmpty'))
    } else {
      toast.error(t('compositions.conflict.generic'))
    }
    return
  }
  toast.error(fallback)
}

async function loadFolders() {
  if (!currentSubjectId.value) return
  loadingFolders.value = true
  try {
    folders.value = await api.listFolders(currentSubjectId.value, scope.value)
    // 高亮题展开选中目录的祖先链，保证它在树中可见。
    if (selectedFolderId.value != null) {
      const chain = folderBreadcrumb(folders.value, selectedFolderId.value)
      expanded.value = new Set([...expanded.value, ...chain.map((f) => f.id)])
    }
  } catch {
    toast.error(t('compositions.toast.loadFoldersFailed'))
  } finally {
    loadingFolders.value = false
  }
}

async function loadCompositions() {
  if (!currentSubjectId.value) return
  loadingList.value = true
  try {
    if (view.value === 'trash') {
      trashed.value = await api.listCompositions(currentSubjectId.value, scope.value, {
        onlyDeleted: true,
      })
    } else {
      compositions.value = await api.listCompositions(currentSubjectId.value, scope.value, {
        folderId: selectedFolderId.value,
        rootOnly: selectedFolderId.value === null,
      })
    }
  } catch {
    toast.error(t('compositions.toast.loadListFailed'))
  } finally {
    loadingList.value = false
  }
}

async function reloadAll() {
  await Promise.all([loadFolders(), loadCompositions()])
}

// onActivated（而非 onMounted）：页面被全局 keepalive 缓存，需要在每次重新激活时刷新数据
onActivated(reloadAll)
watch(currentSubjectId, () => {
  // 文件夹 id 是按学科划分的，切学科时旧的 ?folder= 对新学科无意义
  if (route.query.folder != null) router.replace({ query: {} })
  loadFolders()
})
watch(scope, () => {
  if (route.query.folder != null) router.replace({ query: {} })
  view.value = 'active'
  loadFolders()
})
watch([currentSubjectId, scope, selectedFolderId, view], loadCompositions)

function switchScope(next: string | number) {
  const value = String(next) as CompositionScope
  if (value !== scope.value) router.push(`/compositions/${value}`)
}

function toggleFolder(id: number) {
  const set = new Set(expanded.value)
  if (set.has(id)) set.delete(id)
  else set.add(id)
  expanded.value = set
}

function selectFolder(id: number | null) {
  view.value = 'active'
  router.push({ query: id != null ? { folder: id } : {} })
}

// -------------------------------------------------------------- Folder 弹窗 //
const folderDialog = ref(false)
const folderDialogMode = ref<'create' | 'rename'>('create')
const folderDialogTarget = ref<CompositionFolder | null>(null)
const folderDialogParentId = ref<number | null>(null)
const folderName = ref('')
const folderSubmitting = ref(false)

function openCreateFolder(parentId: number | null) {
  folderDialogMode.value = 'create'
  folderDialogParentId.value = parentId
  folderDialogTarget.value = null
  folderName.value = ''
  folderDialog.value = true
}

function openRenameFolder(folder: CompositionFolder) {
  folderDialogMode.value = 'rename'
  folderDialogTarget.value = folder
  folderName.value = folder.name
  folderDialog.value = true
}

async function submitFolderDialog() {
  if (!currentSubjectId.value || !folderName.value.trim()) {
    toast.error(t('compositions.toast.folderNameRequired'))
    return
  }
  folderSubmitting.value = true
  try {
    if (folderDialogMode.value === 'create') {
      await api.createFolder(currentSubjectId.value, scope.value, {
        name: folderName.value.trim(),
        parent_id: folderDialogParentId.value,
      })
      if (folderDialogParentId.value != null) {
        expanded.value = new Set(expanded.value).add(folderDialogParentId.value)
      }
    } else if (folderDialogTarget.value) {
      await api.updateFolder(currentSubjectId.value, scope.value, folderDialogTarget.value.id, {
        name: folderName.value.trim(),
      })
    }
    folderDialog.value = false
    await loadFolders()
  } catch (err) {
    handleConflict(err, t('compositions.toast.saveFolderFailed'))
  } finally {
    folderSubmitting.value = false
  }
}

async function deleteFolder(folder: CompositionFolder) {
  if (!currentSubjectId.value) return
  if (!window.confirm(t('compositions.confirm.deleteFolder', { name: folder.name }))) return
  try {
    await api.deleteFolder(currentSubjectId.value, scope.value, folder.id)
    toast.success(t('compositions.toast.folderDeleted'))
    if (selectedFolderId.value === folder.id) selectFolder(null)
    await loadFolders()
  } catch (err) {
    handleConflict(err, t('compositions.toast.deleteFolderFailed'))
  }
}

// --------------------------------------------------------------- 移动弹窗 //
const moveDialog = ref(false)
const moveKind = ref<'folder' | 'composition'>('folder')
const moveFolder = ref<CompositionFolder | null>(null)
const moveComposition = ref<Composition | null>(null)
const moveTargetId = ref<number | null>(null)
const moveSubmitting = ref(false)

const moveOptions = computed(() => {
  if (moveKind.value === 'folder' && moveFolder.value) {
    const forbidden = collectDescendantIds(folders.value, moveFolder.value.id)
    forbidden.add(moveFolder.value.id)
    return flatFolderOptions.value.filter((o) => !forbidden.has(o.id))
  }
  return flatFolderOptions.value
})

function openMoveFolder(folder: CompositionFolder) {
  moveKind.value = 'folder'
  moveFolder.value = folder
  moveComposition.value = null
  moveTargetId.value = folder.parent_id
  moveDialog.value = true
}

function openMoveComposition(comp: Composition) {
  moveKind.value = 'composition'
  moveComposition.value = comp
  moveFolder.value = null
  moveTargetId.value = comp.folder_id
  moveDialog.value = true
}

async function submitMove() {
  if (!currentSubjectId.value) return
  moveSubmitting.value = true
  try {
    if (moveKind.value === 'folder' && moveFolder.value) {
      await api.updateFolder(currentSubjectId.value, scope.value, moveFolder.value.id, {
        parent_id: moveTargetId.value,
      })
      await loadFolders()
    } else if (moveKind.value === 'composition' && moveComposition.value) {
      await api.updateComposition(currentSubjectId.value, scope.value, moveComposition.value.id, {
        expected_revision: moveComposition.value.revision,
        folder_id: moveTargetId.value,
      })
      await loadCompositions()
    }
    moveDialog.value = false
    toast.success(t('compositions.toast.moved'))
  } catch (err) {
    handleConflict(err, t('compositions.toast.moveFailed'))
  } finally {
    moveSubmitting.value = false
  }
}

// ----------------------------------------------------------- Composition 弹窗 //
const createDialog = ref(false)
const createTitle = ref('')
const createDescription = ref('')
const createSubmitting = ref(false)

function openCreateComposition() {
  createTitle.value = ''
  createDescription.value = ''
  createDialog.value = true
}

async function submitCreateComposition() {
  if (!currentSubjectId.value || !createTitle.value.trim()) {
    toast.error(t('compositions.toast.titleRequired'))
    return
  }
  createSubmitting.value = true
  try {
    const comp = await api.createComposition(currentSubjectId.value, scope.value, {
      title: createTitle.value.trim(),
      description: createDescription.value.trim() || null,
      folder_id: selectedFolderId.value,
    })
    createDialog.value = false
    router.push(`/compositions/${scope.value}/${comp.id}`)
  } catch (err) {
    handleConflict(err, t('compositions.toast.createFailed'))
  } finally {
    createSubmitting.value = false
  }
}

const editDialog = ref(false)
const editTarget = ref<Composition | null>(null)
const editTitle = ref('')
const editDescription = ref('')
const editSubmitting = ref(false)

function openEditComposition(comp: Composition) {
  editTarget.value = comp
  editTitle.value = comp.title
  editDescription.value = comp.description ?? ''
  editDialog.value = true
}

async function submitEditComposition() {
  if (!currentSubjectId.value || !editTarget.value || !editTitle.value.trim()) {
    toast.error(t('compositions.toast.titleRequired'))
    return
  }
  editSubmitting.value = true
  try {
    await api.updateComposition(currentSubjectId.value, scope.value, editTarget.value.id, {
      expected_revision: editTarget.value.revision,
      title: editTitle.value.trim(),
      description: editDescription.value.trim() || null,
    })
    editDialog.value = false
    await loadCompositions()
    toast.success(t('common.saved'))
  } catch (err) {
    handleConflict(err, t('common.saveFailed'))
  } finally {
    editSubmitting.value = false
  }
}

async function toggleArchive(comp: Composition) {
  if (!currentSubjectId.value) return
  const next = comp.status === 'archived' ? 'draft' : 'archived'
  try {
    await api.updateComposition(currentSubjectId.value, scope.value, comp.id, {
      expected_revision: comp.revision,
      status: next,
    })
    toast.success(next === 'archived' ? t('compositions.toast.archived') : t('compositions.toast.unarchived'))
    await loadCompositions()
  } catch (err) {
    handleConflict(err, t('common.operationFailed'))
  }
}

async function softDelete(comp: Composition) {
  if (!currentSubjectId.value) return
  if (!window.confirm(t('compositions.confirm.moveToTrash', { title: comp.title }))) return
  try {
    await api.deleteComposition(currentSubjectId.value, scope.value, comp.id, comp.revision)
    toast.success(t('compositions.toast.movedToTrash'))
    await loadCompositions()
  } catch (err) {
    handleConflict(err, t('common.deleteFailed'))
  }
}

async function restore(comp: Composition) {
  if (!currentSubjectId.value) return
  try {
    await api.restoreComposition(currentSubjectId.value, scope.value, comp.id, comp.revision)
    toast.success(t('compositions.toast.restored'))
    await loadCompositions()
  } catch (err) {
    handleConflict(err, t('compositions.toast.restoreFailed'))
  }
}

const duplicatingId = ref<number | null>(null)

async function duplicate(comp: Composition) {
  if (!currentSubjectId.value || duplicatingId.value != null) return
  duplicatingId.value = comp.id
  try {
    await api.duplicateComposition(currentSubjectId.value, scope.value, comp.id)
    toast.success(t('compositions.toast.duplicated'))
    await loadCompositions()
  } catch (err) {
    handleConflict(err, t('compositions.toast.duplicateFailed'))
  } finally {
    duplicatingId.value = null
  }
}

function openComposition(comp: Composition) {
  router.push(`/compositions/${scope.value}/${comp.id}`)
}
</script>

<template>
  <PageHeader :title="t('compositions.title')">
    <template #actions>
      <Button
        v-if="currentSubject && view === 'active'"
        size="sm"
        @click="openCreateComposition"
      >
        <Plus class="mr-2 h-4 w-4" /> {{ t('compositions.newComposition') }}
      </Button>
    </template>
  </PageHeader>

  <div class="flex flex-1 flex-col gap-4 px-4 py-4">
    <!-- 无学科守卫：复用全局学科上下文，不自造状态 -->
    <div
      v-if="!currentSubject"
      class="flex flex-1 flex-col items-center justify-center gap-3 py-16 text-center"
    >
      <FileText class="h-10 w-10 text-muted-foreground/50" />
      <p class="text-muted-foreground">
        {{ hasSubjects ? t('compositions.empty.selectSubject') : t('compositions.empty.createSubject') }}
      </p>
    </div>

    <template v-else>
      <!-- scope 切换 + 说明 -->
      <div class="flex flex-wrap items-center justify-between gap-3">
        <Tabs :model-value="scope" @update:model-value="switchScope">
          <TabsList>
            <TabsTrigger value="shared">
              <Users class="mr-1.5 h-4 w-4" /> {{ t('compositions.scope.shared') }}
            </TabsTrigger>
            <TabsTrigger value="personal">
              <Lock class="mr-1.5 h-4 w-4" /> {{ t('compositions.scope.personal') }}
            </TabsTrigger>
          </TabsList>
        </Tabs>
        <p class="text-xs text-muted-foreground">{{ scopeHint }}</p>
      </div>

      <div class="grid flex-1 gap-4 md:grid-cols-[260px_1fr]">
        <!-- 文件夹导航 -->
        <aside class="flex flex-col gap-2 rounded-md border bg-card p-2">
          <div class="flex items-center justify-between px-1">
            <span class="text-xs font-medium text-muted-foreground">{{ t('compositions.folders') }}</span>
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger as-child>
                  <Button variant="ghost" size="icon" class="h-6 w-6" @click="openCreateFolder(null)">
                    <FolderPlus class="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>{{ t('compositions.newRootFolder') }}</TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>

          <button
            type="button"
            class="flex items-center gap-1.5 rounded px-2 py-1 text-sm hover:bg-accent"
            :class="selectedFolderId === null && view === 'active' ? 'bg-accent font-medium' : ''"
            @click="selectFolder(null)"
          >
            <Home class="h-4 w-4 text-muted-foreground" />
            <span>{{ t('compositions.root') }}</span>
          </button>

          <div v-if="loadingFolders" class="flex justify-center py-4">
            <Loader2 class="h-4 w-4 animate-spin text-muted-foreground" />
          </div>
          <CompositionFolderTree
            v-else-if="folderTree.length"
            :nodes="folderTree"
            :selected-id="view === 'active' ? selectedFolderId : null"
            :expanded="expanded"
            @select="selectFolder"
            @toggle="toggleFolder"
            @create-child="openCreateFolder"
            @rename="openRenameFolder"
            @move="openMoveFolder"
            @delete="deleteFolder"
          />
          <p v-else class="px-2 py-2 text-xs text-muted-foreground">{{ t('compositions.noFolders') }}</p>

          <div class="mt-auto border-t pt-2">
            <Button
              variant="ghost"
              size="sm"
              class="w-full justify-start"
              :class="view === 'trash' ? 'bg-accent font-medium' : ''"
              @click="view = 'trash'"
            >
              <Trash class="mr-2 h-4 w-4" /> {{ t('compositions.trash') }}
            </Button>
          </div>
        </aside>

        <!-- 主区：列表 -->
        <section class="flex flex-col gap-3">
          <!-- 面包屑 -->
          <div v-if="view === 'active'" class="flex flex-wrap items-center gap-1 text-sm text-muted-foreground">
            <button class="hover:text-foreground" @click="selectFolder(null)">{{ t('compositions.root') }}</button>
            <template v-for="f in breadcrumb" :key="f.id">
              <span>/</span>
              <button class="hover:text-foreground" @click="selectFolder(f.id)">{{ f.name }}</button>
            </template>
          </div>
          <div v-else class="flex items-center gap-2 text-sm">
            <span class="font-medium">{{ t('compositions.trash') }}</span>
            <Button variant="ghost" size="sm" class="h-7" @click="view = 'active'">{{ t('common.back') }}</Button>
          </div>

          <div v-if="loadingList" class="flex justify-center py-16">
            <Loader2 class="h-6 w-6 animate-spin text-muted-foreground" />
          </div>

          <!-- 回收站列表 -->
          <template v-else-if="view === 'trash'">
            <div v-if="trashed.length" class="divide-y rounded-md border">
              <div
                v-for="comp in trashed"
                :key="comp.id"
                class="flex items-center gap-3 px-3 py-2.5"
              >
                <FileText class="h-4 w-4 shrink-0 text-muted-foreground" />
                <div class="min-w-0 flex-1">
                  <p class="truncate text-sm font-medium">{{ comp.title }}</p>
                  <p class="truncate text-xs text-muted-foreground">
                    {{ t('compositions.deletedAt', { time: comp.deleted_at ? formatRelativeTime(comp.deleted_at) : '' }) }}
                  </p>
                </div>
                <Button variant="outline" size="sm" @click="restore(comp)">
                  <RotateCcw class="mr-1.5 h-4 w-4" /> {{ t('compositions.restore') }}
                </Button>
              </div>
            </div>
            <div v-else class="flex flex-col items-center gap-2 py-16 text-center text-muted-foreground">
              <Trash class="h-8 w-8 opacity-50" />
              <p class="text-sm">{{ t('compositions.trashEmpty') }}</p>
            </div>
          </template>

          <!-- 活动列表 -->
          <template v-else>
            <div v-if="compositions.length" class="divide-y rounded-md border">
              <div
                v-for="comp in compositions"
                :key="comp.id"
                class="group flex items-center gap-3 px-3 py-2.5 hover:bg-accent/50"
              >
                <button
                  type="button"
                  class="flex min-w-0 flex-1 items-center gap-3 text-left"
                  @click="openComposition(comp)"
                >
                  <FileText class="h-4 w-4 shrink-0 text-muted-foreground" />
                  <div class="min-w-0 flex-1">
                    <div class="flex items-center gap-2">
                      <span class="truncate text-sm font-medium">{{ comp.title }}</span>
                      <Badge v-if="comp.status === 'archived'" variant="secondary" class="shrink-0">
                        {{ t('compositions.archived') }}
                      </Badge>
                    </div>
                    <p class="truncate text-xs text-muted-foreground">
                      {{ comp.description || t('compositions.noDescription') }}
                    </p>
                  </div>
                </button>
                <div class="hidden items-center gap-1 text-xs text-muted-foreground sm:flex">
                  <Clock class="h-3.5 w-3.5" />
                  {{ formatRelativeTime(comp.updated_at) }}
                </div>
                <DropdownMenu>
                  <DropdownMenuTrigger as-child @click.stop>
                    <Button variant="ghost" size="icon" class="h-8 w-8">
                      <MoreVertical class="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem @click="openEditComposition(comp)">
                      <Pencil class="mr-2 h-4 w-4" /> {{ t('compositions.actions.editInfo') }}
                    </DropdownMenuItem>
                    <DropdownMenuItem @click="openMoveComposition(comp)">
                      <FolderInput class="mr-2 h-4 w-4" /> {{ t('compositions.actions.move') }}
                    </DropdownMenuItem>
                    <DropdownMenuItem :disabled="duplicatingId === comp.id" @click="duplicate(comp)">
                      <Copy class="mr-2 h-4 w-4" /> {{ t('compositions.actions.duplicate') }}
                    </DropdownMenuItem>
                    <DropdownMenuItem @click="toggleArchive(comp)">
                      <ArchiveRestore v-if="comp.status === 'archived'" class="mr-2 h-4 w-4" />
                      <Archive v-else class="mr-2 h-4 w-4" />
                      {{ comp.status === 'archived' ? t('compositions.actions.unarchive') : t('compositions.actions.archive') }}
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem class="text-destructive" @click="softDelete(comp)">
                      <Trash2 class="mr-2 h-4 w-4" /> {{ t('common.delete') }}
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            </div>
            <div v-else class="flex flex-col items-center gap-3 py-16 text-center text-muted-foreground">
              <FileText class="h-8 w-8 opacity-50" />
              <p class="text-sm">{{ t('compositions.folderEmpty') }}</p>
              <Button size="sm" @click="openCreateComposition">
                <Plus class="mr-2 h-4 w-4" /> {{ t('compositions.newComposition') }}
              </Button>
            </div>
          </template>
        </section>
      </div>
    </template>
  </div>

  <!-- 文件夹 创建/重命名 -->
  <Dialog v-model:open="folderDialog">
    <DialogContent class="sm:max-w-[420px]">
      <DialogHeader>
        <DialogTitle>{{ folderDialogMode === 'create' ? t('compositions.folderDialog.createTitle') : t('compositions.folderDialog.renameTitle') }}</DialogTitle>
      </DialogHeader>
      <div class="space-y-2 py-2">
        <Label>{{ t('common.name') }}</Label>
        <Input v-model="folderName" :placeholder="t('compositions.folderDialog.namePlaceholder')" @keyup.enter="submitFolderDialog" />
      </div>
      <DialogFooter>
        <Button variant="outline" @click="folderDialog = false">{{ t('common.cancel') }}</Button>
        <Button :disabled="folderSubmitting" @click="submitFolderDialog">
          <Loader2 v-if="folderSubmitting" class="mr-2 h-4 w-4 animate-spin" /> {{ t('common.save') }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>

  <!-- 移动 -->
  <Dialog v-model:open="moveDialog">
    <DialogContent class="sm:max-w-[420px]">
      <DialogHeader>
        <DialogTitle>{{ t('compositions.moveDialog.title') }}</DialogTitle>
        <DialogDescription>
          {{ t('compositions.moveDialog.description') }}
        </DialogDescription>
      </DialogHeader>
      <div class="space-y-2 py-2">
        <Select
          :model-value="moveTargetId === null ? '__root__' : String(moveTargetId)"
          @update:model-value="(v) => moveTargetId = v === '__root__' ? null : Number(v)"
        >
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__root__">{{ t('compositions.root') }}</SelectItem>
            <SelectItem v-for="o in moveOptions" :key="o.id" :value="String(o.id)">
              {{ o.label }}
            </SelectItem>
          </SelectContent>
        </Select>
      </div>
      <DialogFooter>
        <Button variant="outline" @click="moveDialog = false">{{ t('common.cancel') }}</Button>
        <Button :disabled="moveSubmitting" @click="submitMove">
          <Loader2 v-if="moveSubmitting" class="mr-2 h-4 w-4 animate-spin" /> {{ t('compositions.actions.move') }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>

  <!-- 新建组稿 -->
  <Dialog v-model:open="createDialog">
    <DialogContent class="sm:max-w-[460px]">
      <DialogHeader>
        <DialogTitle>{{ t('compositions.newComposition') }}</DialogTitle>
        <DialogDescription>{{ scopeHint }}</DialogDescription>
      </DialogHeader>
      <div class="space-y-4 py-2">
        <div class="space-y-2">
          <Label>{{ t('compositions.form.title') }}</Label>
          <Input v-model="createTitle" :placeholder="t('compositions.form.titleExample')" @keyup.enter="submitCreateComposition" />
        </div>
        <div class="space-y-2">
          <Label>{{ t('compositions.form.description') }}</Label>
          <Textarea v-model="createDescription" :placeholder="t('compositions.form.descriptionPlaceholder')" rows="3" />
        </div>
      </div>
      <DialogFooter>
        <Button variant="outline" @click="createDialog = false">{{ t('common.cancel') }}</Button>
        <Button :disabled="createSubmitting" @click="submitCreateComposition">
          <Loader2 v-if="createSubmitting" class="mr-2 h-4 w-4 animate-spin" /> {{ t('compositions.form.createAndOpen') }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>

  <!-- 编辑组稿元数据 -->
  <Dialog v-model:open="editDialog">
    <DialogContent class="sm:max-w-[460px]">
      <DialogHeader>
        <DialogTitle>{{ t('compositions.form.editTitle') }}</DialogTitle>
      </DialogHeader>
      <div class="space-y-4 py-2">
        <div class="space-y-2">
          <Label>{{ t('compositions.form.title') }}</Label>
          <Input v-model="editTitle" :placeholder="t('compositions.form.titlePlaceholder')" />
        </div>
        <div class="space-y-2">
          <Label>{{ t('compositions.form.description') }}</Label>
          <Textarea v-model="editDescription" :placeholder="t('compositions.form.descriptionPlaceholder')" rows="3" />
        </div>
      </div>
      <DialogFooter>
        <Button variant="outline" @click="editDialog = false">{{ t('common.cancel') }}</Button>
        <Button :disabled="editSubmitting" @click="submitEditComposition">
          <Loader2 v-if="editSubmitting" class="mr-2 h-4 w-4 animate-spin" /> {{ t('common.save') }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
