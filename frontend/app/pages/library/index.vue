<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import PageHeader from '~/components/PageHeader.vue'
import { Button } from '@/components/ui/button'
import { Card, CardHeader, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Plus, MoreVertical, Copy, Archive, ArchiveRestore, Trash2, FileText, Package, FolderPlus, Folder as FolderIcon, Loader2, ChevronRight,
} from '@lucide/vue'
import { toast } from 'vue-sonner'
import { useCompositions } from '~/composables/useCompositions'
import { useFolders } from '~/composables/useFolders'
import { formatRelativeTime } from '@/lib/utils'
import type { Composition, Folder, CompType, CompositionScope } from '~/types'

const route = useRoute()
const router = useRouter()
const { list, create, update, remove, duplicate } = useCompositions()
const { list: listFolders, create: createFolder } = useFolders()
const { currentSubjectId } = useSubjectContext()

const kind = computed<'component' | 'deliverable'>(
  () => (route.query.type === 'group' ? 'component' : 'deliverable'),
)
const isComponent = computed(() => kind.value === 'component')

const scope = ref<CompositionScope>((route.query.scope as CompositionScope) || 'personal')
const compTypeFilter = ref<CompType | 'all'>('all')
const activeFolderId = ref<number | 'all'>('all')

const folders = ref<Folder[]>([])
const items = ref<Composition[]>([])
const loading = ref(false)

const compTypeLabels: Record<string, string> = {
  question_group: '题组', exam_paper: '试卷', study_guide: '学案', handout: '专题讲义',
}

const loadFolders = async () => {
  try {
    folders.value = await listFolders({
      kind: kind.value,
      subject_id: currentSubjectId.value,
      scope: isComponent.value ? undefined : scope.value,
    })
  } catch {
    folders.value = []
  }
}

const loadItems = async () => {
  loading.value = true
  try {
    items.value = await list({
      kind: kind.value,
      scope: isComponent.value ? undefined : scope.value,
      subject_id: currentSubjectId.value,
      comp_type: compTypeFilter.value === 'all' ? undefined : compTypeFilter.value,
      folder_id: activeFolderId.value === 'all' ? undefined : activeFolderId.value,
      sort: 'updated_desc',
    })
  } catch {
    toast.error('加载失败')
  } finally {
    loading.value = false
  }
}

const reload = async () => {
  await loadFolders()
  await loadItems()
}

onMounted(reload)
watch(currentSubjectId, reload)
watch(() => route.query.type, () => {
  compTypeFilter.value = 'all'
  activeFolderId.value = 'all'
  reload()
})
watch(() => route.query.scope, (v) => {
  if (v) scope.value = v as CompositionScope
  reload()
})

const setScope = (v: string | number) => {
  scope.value = v as CompositionScope
  activeFolderId.value = 'all'
  router.replace({ query: { ...route.query, scope: scope.value } })
}

const setCompType = (v: string | number) => {
  compTypeFilter.value = v as CompType | 'all'
  loadItems()
}

const selectFolder = (id: number | 'all') => {
  activeFolderId.value = id
  loadItems()
}

const editItem = (item: Composition) => {
  router.push(isComponent.value ? `/groups/${item.id}/edit` : `/papers/${item.id}/edit`)
}

const defaultCompType = computed<CompType>(() => (isComponent.value ? 'question_group' : 'exam_paper'))

const createItem = async (comp_type: CompType) => {
  try {
    const item = await create({
      title: `新${compTypeLabels[comp_type]} ${new Date().toLocaleDateString()}`,
      comp_type,
      subject_id: currentSubjectId.value ?? null,
      scope: isComponent.value ? null : scope.value,
      folder_id: activeFolderId.value === 'all' ? null : activeFolderId.value,
    })
    editItem(item)
  } catch {
    toast.error('创建失败')
  }
}

const newFolder = async () => {
  const name = window.prompt('新建文件夹名称')
  if (!name) return
  try {
    await createFolder({
      name,
      kind: kind.value,
      subject_id: currentSubjectId.value as number,
      scope: isComponent.value ? null : scope.value,
      parent_id: null,
    })
    toast.success('已创建文件夹')
    loadFolders()
  } catch {
    toast.error('创建文件夹失败')
  }
}

const renameItem = async (item: Composition) => {
  const title = window.prompt('重命名', item.title)
  if (!title || title === item.title) return
  try {
    await update(item.id, { title })
    loadItems()
  } catch {
    toast.error('重命名失败')
  }
}

const duplicateItem = async (id: number) => {
  try {
    await duplicate(id)
    toast.success('已复制')
    loadItems()
  } catch {
    toast.error('复制失败')
  }
}

const toggleArchive = async (item: Composition) => {
  try {
    await update(item.id, { status: item.status === 'archived' ? 'draft' : 'archived' })
    loadItems()
  } catch {
    toast.error('操作失败')
  }
}

const deleteItem = async (item: Composition) => {
  if (!window.confirm(`确定删除《${item.title}》吗？此操作不可恢复。`)) return
  try {
    await remove(item.id)
    toast.success('已删除')
    loadItems()
  } catch {
    toast.error('删除失败')
  }
}

const pageTitle = computed(() => (isComponent.value ? '题组' : '作品库'))
</script>

<template>
  <PageHeader :title="pageTitle">
    <template #actions>
      <DropdownMenu>
        <DropdownMenuTrigger as-child>
          <Button size="sm">
            <Plus class="mr-2 h-4 w-4" /> 新建
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <template v-if="isComponent">
            <DropdownMenuItem @click="createItem('question_group')">新建题组</DropdownMenuItem>
          </template>
          <template v-else>
            <DropdownMenuItem @click="createItem('exam_paper')">新建试卷</DropdownMenuItem>
            <DropdownMenuItem @click="createItem('study_guide')">新建学案</DropdownMenuItem>
            <DropdownMenuItem @click="createItem('handout')">新建专题讲义</DropdownMenuItem>
          </template>
        </DropdownMenuContent>
      </DropdownMenu>
    </template>
  </PageHeader>

  <div class="flex flex-1 overflow-hidden">
    <!-- Left: folder tree -->
    <aside class="w-56 shrink-0 border-r overflow-y-auto p-3 space-y-1">
      <div class="flex items-center justify-between mb-2">
        <span class="text-xs font-medium text-muted-foreground">文件夹</span>
        <Button variant="ghost" size="icon" class="h-6 w-6" @click="newFolder">
          <FolderPlus class="h-4 w-4" />
        </Button>
      </div>
      <button
        :class="['w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-sm text-left', activeFolderId === 'all' ? 'bg-primary/10 text-primary' : 'hover:bg-muted']"
        @click="selectFolder('all')"
      >
        <FolderIcon class="h-4 w-4" /> 全部
      </button>
      <button
        v-for="f in folders"
        :key="f.id"
        :class="['w-full flex items-center gap-2 px-2 py-1.5 rounded-md text-sm text-left', activeFolderId === f.id ? 'bg-primary/10 text-primary' : 'hover:bg-muted']"
        :style="{ paddingLeft: (f.parent_id ? 1.75 : 0.5) + 'rem' }"
        @click="selectFolder(f.id)"
      >
        <ChevronRight v-if="f.parent_id" class="h-3 w-3 opacity-50" />
        <FolderIcon class="h-4 w-4" /> <span class="truncate">{{ f.name }}</span>
      </button>
    </aside>

    <!-- Right: content -->
    <div class="flex flex-1 flex-col overflow-y-auto px-4 py-4 space-y-4">
      <div class="flex items-center justify-between gap-4 flex-wrap">
        <Tabs v-if="!isComponent" :model-value="scope" @update:model-value="setScope">
          <TabsList>
            <TabsTrigger value="team">团队空间</TabsTrigger>
            <TabsTrigger value="personal">我的空间</TabsTrigger>
          </TabsList>
        </Tabs>

        <Tabs v-if="!isComponent" :model-value="compTypeFilter" @update:model-value="setCompType">
          <TabsList>
            <TabsTrigger value="all">全部</TabsTrigger>
            <TabsTrigger value="exam_paper">试卷</TabsTrigger>
            <TabsTrigger value="study_guide">学案</TabsTrigger>
            <TabsTrigger value="handout">讲义</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      <div v-if="loading" class="flex justify-center py-16">
        <Loader2 class="h-8 w-8 animate-spin text-muted-foreground" />
      </div>

      <div
        v-else-if="items.length > 0"
        class="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
      >
        <Card
          v-for="item in items"
          :key="item.id"
          class="group hover:shadow-lg transition-shadow cursor-pointer"
          @click="editItem(item)"
        >
          <CardHeader class="pb-3">
            <div class="flex items-start justify-between">
              <Badge variant="outline" class="gap-1">
                <Package v-if="isComponent" class="h-3 w-3" />
                <FileText v-else class="h-3 w-3" />
                {{ compTypeLabels[item.comp_type] || item.comp_type }}
              </Badge>
              <DropdownMenu>
                <DropdownMenuTrigger as-child @click.stop>
                  <Button variant="ghost" size="icon" class="h-8 w-8 opacity-0 group-hover:opacity-100">
                    <MoreVertical class="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" @click.stop>
                  <DropdownMenuItem @click="renameItem(item)">重命名</DropdownMenuItem>
                  <DropdownMenuItem @click="duplicateItem(item.id)">
                    <Copy class="mr-2 h-4 w-4" /> 复制
                  </DropdownMenuItem>
                  <DropdownMenuItem @click="toggleArchive(item)">
                    <ArchiveRestore v-if="item.status === 'archived'" class="mr-2 h-4 w-4" />
                    <Archive v-else class="mr-2 h-4 w-4" />
                    {{ item.status === 'archived' ? '取消归档' : '归档' }}
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem class="text-destructive" @click="deleteItem(item)">
                    <Trash2 class="mr-2 h-4 w-4" /> 删除
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </CardHeader>
          <CardContent>
            <h3 class="font-medium truncate">{{ item.title }}</h3>
            <div class="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
              <Badge variant="secondary">{{ item.block_count }} 项</Badge>
              <span>{{ formatRelativeTime(item.updated_at) }}</span>
            </div>
          </CardContent>
        </Card>
      </div>

      <div v-else class="flex flex-col items-center justify-center py-16 text-center text-muted-foreground">
        <p class="mb-4">这里还没有内容</p>
        <Button @click="createItem(defaultCompType)">
          <Plus class="mr-2 h-4 w-4" /> 新建{{ compTypeLabels[defaultCompType] }}
        </Button>
      </div>
    </div>
  </div>
</template>
