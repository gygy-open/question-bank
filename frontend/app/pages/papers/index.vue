<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import PageHeader from '~/components/PageHeader.vue'
import { Button } from '@/components/ui/button'
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  Plus, MoreVertical, Pencil, Copy, Archive, ArchiveRestore, Trash2, FileText, Clock, Edit, Loader2, TriangleAlert,
} from '@lucide/vue'
import { toast } from 'vue-sonner'
import { usePapers } from '~/composables/usePapers'
import { formatRelativeTime } from '@/lib/utils'
import type { Paper, Subject } from '~/types'

const { list, create, update, remove, duplicate } = usePapers()
const { data: subjects } = await useAPI<Subject[]>('/subjects')
const { currentSubjectId } = useSubjectContext()

const papers = ref<Paper[]>([])
const loading = ref(false)
const activeTab = ref<'draft' | 'archived'>('draft')
const sortBy = ref('updated_desc')

const createOpen = ref(false)
const creating = ref(false)
const form = ref<{ title: string; subject_id?: number; description: string }>({
  title: '', subject_id: undefined, description: '',
})

const filteredPapers = computed(() => papers.value)

const loadPapers = async () => {
  loading.value = true
  try {
    papers.value = await list({
      subject_id: currentSubjectId.value,
      status: activeTab.value,
      sort: sortBy.value,
    })
  } catch {
    toast.error('加载试卷失败')
  } finally {
    loading.value = false
  }
}

onMounted(loadPapers)

// Reload when the global subject switches (e.g. via the sidebar selector).
watch(currentSubjectId, loadPapers)

const onTabChange = (v: string | number) => {
  activeTab.value = v as 'draft' | 'archived'
  loadPapers()
}

const onSortChange = () => loadPapers()

const openCreate = () => {
  form.value = { title: '', subject_id: currentSubjectId.value ?? undefined, description: '' }
  createOpen.value = true
}

const submitCreate = async () => {
  if (!form.value.title.trim()) {
    toast.error('请输入试卷标题')
    return
  }
  creating.value = true
  try {
    const paper = await create({
      title: form.value.title,
      subject_id: form.value.subject_id ?? null,
      description: form.value.description || null,
    })
    createOpen.value = false
    navigateTo(`/papers/${paper.id}/edit`)
  } catch {
    toast.error('创建失败')
  } finally {
    creating.value = false
  }
}

const editPaper = (id: number) => navigateTo(`/papers/${id}/edit`)

const renamePaper = async (paper: Paper) => {
  const title = window.prompt('重命名试卷', paper.title)
  if (!title || title === paper.title) return
  try {
    await update(paper.id, { title })
    toast.success('已重命名')
    loadPapers()
  } catch {
    toast.error('重命名失败')
  }
}

const duplicatePaper = async (id: number) => {
  try {
    await duplicate(id)
    toast.success('已复制')
    loadPapers()
  } catch {
    toast.error('复制失败')
  }
}

const toggleArchive = async (paper: Paper) => {
  try {
    await update(paper.id, { status: paper.status === 'archived' ? 'draft' : 'archived' })
    toast.success(paper.status === 'archived' ? '已取消归档' : '已归档')
    loadPapers()
  } catch {
    toast.error('操作失败')
  }
}

const deletePaper = async (paper: Paper) => {
  if (!window.confirm(`确定删除《${paper.title}》吗？此操作不可恢复。`)) return
  try {
    await remove(paper.id)
    toast.success('已删除')
    loadPapers()
  } catch {
    toast.error('删除失败')
  }
}
</script>

<template>
  <PageHeader title="我的试卷">
    <template #actions>
      <Button size="sm" @click="openCreate">
        <Plus class="mr-2 h-4 w-4" />
        新建试卷
      </Button>
    </template>
  </PageHeader>

  <div class="flex flex-1 flex-col px-4 py-6 space-y-6">
    <Alert class="items-center [&>svg]:translate-y-0">
      <TriangleAlert class="h-4 w-4" />
      <AlertDescription class="flex items-center justify-between gap-2 flex-wrap">
        <span class="text-sm">试卷（旧版）功能即将停用，请尽快将试卷手动迁移到组稿工作台，以免更新后无法使用。</span>
        <Button size="sm" variant="outline" as-child>
          <NuxtLink to="/compositions/personal">前往组稿工作台</NuxtLink>
        </Button>
      </AlertDescription>
    </Alert>

    <div class="flex items-center justify-between gap-4 flex-wrap">
      <Tabs :model-value="activeTab" @update:model-value="onTabChange">
        <TabsList>
          <TabsTrigger value="draft">进行中</TabsTrigger>
          <TabsTrigger value="archived">已归档</TabsTrigger>
        </TabsList>
      </Tabs>

      <Select v-model="sortBy" @update:model-value="onSortChange">
        <SelectTrigger class="w-[160px]">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="updated_desc">最近编辑</SelectItem>
          <SelectItem value="created_desc">创建时间</SelectItem>
          <SelectItem value="title_asc">标题 A-Z</SelectItem>
        </SelectContent>
      </Select>
    </div>

    <div v-if="loading" class="flex justify-center py-16">
      <Loader2 class="h-8 w-8 animate-spin text-muted-foreground" />
    </div>

    <div
      v-else-if="filteredPapers.length > 0"
      class="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
    >
      <Card
        v-for="paper in filteredPapers"
        :key="paper.id"
        class="group hover:shadow-lg transition-shadow cursor-pointer"
        @click="editPaper(paper.id)"
      >
        <CardHeader class="pb-3">
          <div class="flex items-start justify-between">
            <Badge variant="outline">
              {{ subjects?.find(s => s.id === paper.subject_id)?.name || '未分类' }}
            </Badge>
            <DropdownMenu>
              <DropdownMenuTrigger as-child @click.stop>
                <Button variant="ghost" size="icon" class="h-8 w-8 opacity-0 group-hover:opacity-100">
                  <MoreVertical class="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem @click.stop="renamePaper(paper)">
                  <Pencil class="mr-2 h-4 w-4" /> 重命名
                </DropdownMenuItem>
                <DropdownMenuItem @click.stop="duplicatePaper(paper.id)">
                  <Copy class="mr-2 h-4 w-4" /> 复制
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem @click.stop="toggleArchive(paper)">
                  <ArchiveRestore v-if="paper.status === 'archived'" class="mr-2 h-4 w-4" />
                  <Archive v-else class="mr-2 h-4 w-4" />
                  {{ paper.status === 'archived' ? '取消归档' : '归档' }}
                </DropdownMenuItem>
                <DropdownMenuItem class="text-destructive" @click.stop="deletePaper(paper)">
                  <Trash2 class="mr-2 h-4 w-4" /> 删除
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
          <CardTitle class="mt-2 text-lg line-clamp-1">{{ paper.title }}</CardTitle>
          <CardDescription class="line-clamp-2 min-h-[2.5rem]">
            {{ paper.description || '暂无描述' }}
          </CardDescription>
        </CardHeader>

        <CardContent>
          <div class="flex items-center gap-4 text-sm text-muted-foreground">
            <div class="flex items-center gap-1">
              <FileText class="h-4 w-4" />
              <span>{{ paper.question_count }} 题</span>
            </div>
            <div class="flex items-center gap-1">
              <Clock class="h-4 w-4" />
              <span>{{ formatRelativeTime(paper.updated_at) }}</span>
            </div>
          </div>
        </CardContent>

        <CardFooter class="pt-3 border-t">
          <Button variant="outline" class="w-full" @click.stop="editPaper(paper.id)">
            <Edit class="mr-2 h-4 w-4" /> 编辑试卷
          </Button>
        </CardFooter>
      </Card>
    </div>

    <div v-else class="flex flex-col items-center justify-center py-16 text-center">
      <FileText class="h-12 w-12 text-muted-foreground/50 mb-4" />
      <p class="text-muted-foreground mb-4">
        {{ activeTab === 'archived' ? '没有已归档的试卷' : '还没有试卷' }}
      </p>
      <Button v-if="activeTab === 'draft'" @click="openCreate">
        <Plus class="mr-2 h-4 w-4" /> 新建试卷
      </Button>
    </div>
  </div>

  <Dialog v-model:open="createOpen">
    <DialogContent class="sm:max-w-[425px]">
      <DialogHeader>
        <DialogTitle>新建试卷</DialogTitle>
      </DialogHeader>
      <div class="space-y-4 py-2">
        <div class="space-y-2">
          <Label>标题</Label>
          <Input v-model="form.title" placeholder="例如：期中考试" />
        </div>
        <div class="space-y-2">
          <Label>学科</Label>
          <Select v-model="form.subject_id">
            <SelectTrigger>
              <SelectValue placeholder="选择学科（可选）" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="s in subjects" :key="s.id" :value="s.id">
                {{ s.name }}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div class="space-y-2">
          <Label>描述</Label>
          <Textarea v-model="form.description" placeholder="试卷说明（可选）" rows="3" />
        </div>
      </div>
      <DialogFooter>
        <Button variant="outline" @click="createOpen = false">取消</Button>
        <Button :disabled="creating" @click="submitCreate">
          <Loader2 v-if="creating" class="mr-2 h-4 w-4 animate-spin" />
          创建并编辑
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
