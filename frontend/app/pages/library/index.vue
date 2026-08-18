<script setup lang="ts">
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import PageHeader from '~/components/PageHeader.vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ButtonGroup } from '@/components/ui/button-group'
import LibraryFolderTreeItem from '~/components/LibraryFolderTreeItem.vue'
import LibraryItemCard from '~/components/LibraryItemCard.vue'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Plus, ChevronDown, FolderPlus, Folder as FolderIcon, Loader2, Check, X, Search, LayoutGrid, List,
} from '@lucide/vue'
import { toast } from 'vue-sonner'
import { useCompositions } from '~/composables/useCompositions'
import { useFolders } from '~/composables/useFolders'
import type { Composition, Folder, TemplateItem } from '~/types'

interface FolderNode extends Folder {
  children: FolderNode[]
}

const route = useRoute()
const router = useRouter()
const { list, create: createComposition, update, remove, duplicate, listTemplates, createFromTemplate, saveAsTemplate } = useCompositions()
const { list: listFolders, create: createFolder, update: updateFolder, remove: removeFolder } = useFolders()
const { currentSubjectId } = useSubjectContext()

// Removed 'kind' - everything is now just a composition in a space
const scope = ref<'team' | 'personal'>((route.query.scope as 'team' | 'personal') || 'personal')
const activeFolderId = ref<number | 'all'>('all')

const folders = ref<Folder[]>([])
const items = ref<Composition[]>([])
const templates = ref<TemplateItem[]>([])
const loading = ref(false)
const keyword = ref('')
const viewMode = ref<'grid' | 'list'>((typeof window !== 'undefined' && localStorage.getItem('library-view-mode') as 'grid' | 'list') || 'grid')
watch(viewMode, (v) => {
  if (typeof window !== 'undefined') localStorage.setItem('library-view-mode', v)
})

const systemTemplates = computed(() => templates.value.filter((t) => t.source === 'system'))
const customTemplates = computed(() => templates.value.filter((t) => t.source === 'custom'))

// Flat folders list -> nested tree grouped by parent_id, for the sidebar.
const folderTree = computed<FolderNode[]>(() => {
  const map = new Map<number, FolderNode>()
  folders.value.forEach((f) => map.set(f.id, { ...f, children: [] }))
  const roots: FolderNode[] = []
  folders.value.forEach((f) => {
    const node = map.get(f.id)!
    if (f.parent_id && map.has(f.parent_id)) {
      map.get(f.parent_id)!.children.push(node)
    } else {
      roots.push(node)
    }
  })
  return roots
})

const loadFolders = async () => {
  try {
    folders.value = await listFolders({
      subject_id: currentSubjectId.value,
      scope: scope.value,
    })
  } catch {
    folders.value = []
  }
}

const loadItems = async () => {
  loading.value = true
  try {
    items.value = await list({
      subject_id: currentSubjectId.value,
      scope: scope.value,
      folder_id: activeFolderId.value === 'all' ? undefined : activeFolderId.value,
      keyword: keyword.value.trim() || undefined,
      sort: 'updated_desc',
    })
  } catch {
    toast.error('加载失败')
  } finally {
    loading.value = false
  }
}

let searchDebounce: ReturnType<typeof setTimeout> | null = null
watch(keyword, () => {
  if (searchDebounce) clearTimeout(searchDebounce)
  searchDebounce = setTimeout(loadItems, 300)
})

const loadTemplates = async () => {
  try {
    templates.value = await listTemplates(currentSubjectId.value)
  } catch {
    templates.value = []
  }
}

const reload = async () => {
  await loadFolders()
  await loadTemplates()
  await loadItems()
}

onMounted(reload)
watch(currentSubjectId, reload)

watch(() => route.query.scope, (v) => {
  if (v) scope.value = v as 'team'|'personal'
  activeFolderId.value = 'all'
  reload()
})

const setScope = (v: string | number) => {
  scope.value = v as 'team'|'personal'
  activeFolderId.value = 'all'
  router.replace({ query: { ...route.query, scope: scope.value } })
}

const selectFolder = (id: number | 'all') => {
  activeFolderId.value = id
  loadItems()
}

const editItem = (item: Composition) => {
  router.push(`/composition/${item.id}/edit`)
}

const createFromTemplateItem = async (t: TemplateItem) => {
  try {
    const item = await createFromTemplate({
      source: t.source,
      key: t.key ?? undefined,
      template_id: t.id ?? undefined,
      subject_id: currentSubjectId.value ?? null,
      scope: scope.value,
      folder_id: activeFolderId.value === 'all' ? null : activeFolderId.value,
    })
    editItem(item)
  } catch {
    toast.error('创建失败')
  }
}

// Primary button and per-folder "+" create a blank untitled item directly, Notion-style, skipping the template picker.
const createBlankItem = async (folderId?: number) => {
  try {
    const item = await createComposition({
      title: '未命名标题',
      folder_id: folderId ?? (activeFolderId.value === 'all' ? null : activeFolderId.value),
      subject_id: currentSubjectId.value ?? null,
      scope: scope.value,
    })
    editItem(item)
  } catch {
    toast.error('创建失败')
  }
}

const quickCreate = () => createBlankItem()
const quickCreateInFolder = (folderId: number) => createBlankItem(folderId)

const saveAsTemplateItem = async (item: Composition) => {
  try {
    await saveAsTemplate(item.id, { scope: scope.value })
    toast.success('已存为模板')
    loadTemplates()
  } catch {
    toast.error('存为模板失败')
  }
}

const editingFolder = ref(false)
const newFolderName = ref('')
const newFolderInputRef = ref<any>(null)

const startNewFolder = async () => {
  newFolderName.value = ''
  editingFolder.value = true
  await nextTick()
  newFolderInputRef.value?.$el?.focus()
}

const cancelNewFolder = () => {
  editingFolder.value = false
}

const saveNewFolder = async () => {
  const name = newFolderName.value.trim()
  if (!name) {
    editingFolder.value = false
    return
  }
  try {
    await createFolder({
      name,
      subject_id: currentSubjectId.value as number,
      scope: scope.value,
      parent_id: null,
    })
    toast.success('已创建文件夹')
    editingFolder.value = false
    loadFolders()
  } catch {
    toast.error('创建文件夹失败')
  }
}

const renameFolder = async (id: number, name: string) => {
  try {
    await updateFolder(id, { name })
    toast.success('已重命名')
    loadFolders()
  } catch {
    toast.error('重命名失败')
  }
}

const createSubfolder = async (parentId: number, name: string) => {
  try {
    await createFolder({
      name,
      subject_id: currentSubjectId.value as number,
      scope: scope.value,
      parent_id: parentId,
    })
    toast.success('已创建文件夹')
    loadFolders()
  } catch {
    toast.error('创建文件夹失败')
  }
}

const deleteFolder = async (id: number) => {
  try {
    await removeFolder(id)
    toast.success('已删除文件夹')
    if (activeFolderId.value === id) activeFolderId.value = 'all'
    await loadFolders()
    loadItems()
  } catch {
    toast.error('删除文件夹失败')
  }
}

// Dropping a card from the grid/list onto a folder row moves it there.
const moveItemToFolder = async (folderId: number, itemId: number) => {
  const item = items.value.find((i) => i.id === itemId)
  if (!item || item.folder_id === folderId) return
  const previousFolderId = item.folder_id
  item.folder_id = folderId
  if (activeFolderId.value !== 'all' && activeFolderId.value !== folderId) {
    items.value = items.value.filter((i) => i.id !== itemId)
  }
  try {
    await update(itemId, { folder_id: folderId })
    toast.success('已移动')
  } catch {
    item.folder_id = previousFolderId
    toast.error('移动失败')
    loadItems()
  }
}

const applyRename = async (item: Composition, title: string) => {
  const previous = item.title
  item.title = title
  try {
    await update(item.id, { title })
  } catch {
    item.title = previous
    toast.error('重命名失败')
  }
}

const duplicateItem = async (id: number) => {
  try {
    const copy = await duplicate(id)
    items.value.unshift(copy)
    toast.success('已复制')
  } catch {
    toast.error('复制失败')
  }
}

const toggleArchive = async (item: Composition) => {
  const previous = item.status
  const next = item.status === 'archived' ? 'draft' : 'archived'
  item.status = next
  try {
    await update(item.id, { status: next })
  } catch {
    item.status = previous
    toast.error('操作失败')
  }
}

// Deletion is optimistic with an undo window instead of a blocking confirm dialog.
const pendingDeletes = new Map<number, { item: Composition, index: number, timer: ReturnType<typeof setTimeout> }>()

const finalizeDelete = async (id: number) => {
  if (!pendingDeletes.delete(id)) return
  try {
    await remove(id)
  } catch {
    toast.error('删除失败')
    loadItems()
  }
}

const undoDelete = (id: number) => {
  const pending = pendingDeletes.get(id)
  if (!pending) return
  clearTimeout(pending.timer)
  pendingDeletes.delete(id)
  items.value.splice(pending.index, 0, pending.item)
}

const deleteItem = (item: Composition) => {
  const index = items.value.findIndex((i) => i.id === item.id)
  if (index === -1) return
  items.value.splice(index, 1)
  const timer = setTimeout(() => finalizeDelete(item.id), 4000)
  pendingDeletes.set(item.id, { item, index, timer })
  toast.success(`已删除《${item.title}》`, {
    action: { label: '撤销', onClick: () => undoDelete(item.id) },
    duration: 4000,
  })
}

const pageTitle = computed(() => '教研资产库')
</script>

<template>
  <PageHeader :title="pageTitle">
    <template #actions>
      <Tabs :model-value="scope" @update:model-value="setScope">
        <TabsList>
          <TabsTrigger value="personal">我的空间</TabsTrigger>
          <TabsTrigger value="team">团队空间</TabsTrigger>
        </TabsList>
      </Tabs>
      <ButtonGroup>
        <Button size="sm" @click="quickCreate">
          <Plus class="mr-2 h-4 w-4" /> 新建教研资产
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger as-child>
            <Button size="sm" variant="outline" class="px-2" title="从模板新建">
              <ChevronDown class="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel>系统模板</DropdownMenuLabel>
            <DropdownMenuItem v-for="t in systemTemplates" :key="t.key || t.label" @click="createFromTemplateItem(t)">
              {{ t.label }}
            </DropdownMenuItem>
            <template v-if="customTemplates.length">
              <DropdownMenuSeparator />
              <DropdownMenuLabel>我的模板</DropdownMenuLabel>
              <DropdownMenuItem v-for="t in customTemplates" :key="t.id" @click="createFromTemplateItem(t)">
                {{ t.label }}
              </DropdownMenuItem>
            </template>
          </DropdownMenuContent>
        </DropdownMenu>
      </ButtonGroup>
    </template>
  </PageHeader>

  <div class="flex flex-1 overflow-hidden">
    <!-- Left: folder tree -->
    <aside class="w-56 shrink-0 border-r overflow-y-auto p-3 space-y-1">
      <div class="flex items-center justify-between mb-2">
        <span class="text-xs font-medium text-muted-foreground">文件夹</span>
        <Button variant="ghost" size="icon" class="h-6 w-6" @click="startNewFolder">
          <FolderPlus class="h-4 w-4" />
        </Button>
      </div>
      <div v-if="editingFolder" class="flex items-center gap-1 mb-1">
        <Input
          ref="newFolderInputRef"
          v-model="newFolderName"
          class="h-7 text-sm"
          placeholder="文件夹名称"
          @keyup.enter="saveNewFolder"
          @keyup.esc="cancelNewFolder"
        />
        <Button size="icon" variant="ghost" class="h-7 w-7 shrink-0 text-green-600" @click="saveNewFolder">
          <Check class="h-4 w-4" />
        </Button>
        <Button size="icon" variant="ghost" class="h-7 w-7 shrink-0 text-muted-foreground" @click="cancelNewFolder">
          <X class="h-4 w-4" />
        </Button>
      </div>
      <button
        :class="['w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-sm text-left', activeFolderId === 'all' ? 'bg-primary/10 text-primary' : 'hover:bg-muted']"
        @click="selectFolder('all')"
      >
        <FolderIcon class="h-4 w-4" /> 全部
      </button>
      <LibraryFolderTreeItem
        v-for="node in folderTree"
        :key="node.id"
        :folder="node"
        :active-folder-id="activeFolderId"
        @select="selectFolder"
        @rename="renameFolder"
        @delete="deleteFolder"
        @create="createSubfolder"
        @create-item="quickCreateInFolder"
        @drop-item="moveItemToFolder"
      />
    </aside>

    <!-- Right: content -->
    <div class="flex flex-1 flex-col overflow-y-auto px-4 py-4 space-y-4">
      <div class="flex items-center gap-2">
        <div class="relative w-72">
          <Search class="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input v-model="keyword" placeholder="搜索教研资产..." class="pl-8 h-9" />
        </div>
        <div class="ml-auto flex items-center gap-0.5 rounded-md border p-0.5">
          <Button :variant="viewMode === 'grid' ? 'secondary' : 'ghost'" size="icon" class="h-7 w-7" title="网格视图" @click="viewMode = 'grid'">
            <LayoutGrid class="h-4 w-4" />
          </Button>
          <Button :variant="viewMode === 'list' ? 'secondary' : 'ghost'" size="icon" class="h-7 w-7" title="列表视图" @click="viewMode = 'list'">
            <List class="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div v-if="loading" class="flex justify-center py-16">
        <Loader2 class="h-8 w-8 animate-spin text-muted-foreground" />
      </div>

      <div
        v-else-if="items.length > 0"
        :class="viewMode === 'grid' ? 'grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4' : 'flex flex-col gap-2'"
      >
        <LibraryItemCard
          v-for="item in items"
          :key="item.id"
          :item="item"
          :view="viewMode"
          @open="editItem(item)"
          @rename="(title) => applyRename(item, title)"
          @duplicate="duplicateItem(item.id)"
          @save-as-template="saveAsTemplateItem(item)"
          @toggle-archive="toggleArchive(item)"
          @delete="deleteItem(item)"
        />
      </div>

      <div v-else class="flex flex-col items-center justify-center py-16 text-center text-muted-foreground">
        <p v-if="keyword.trim()">未找到匹配「{{ keyword }}」的教研资产</p>
        <p v-else>这里还没有内容，点击右上角「新建教研资产」开始</p>
      </div>
    </div>
  </div>
</template>
