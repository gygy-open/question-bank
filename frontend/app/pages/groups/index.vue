<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import PageHeader from '~/components/PageHeader.vue'
import { Button } from '@/components/ui/button'
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
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
import {
  Plus, MoreVertical, Pencil, Copy, Trash2, Package, Clock, Edit, Loader2, ShoppingBasket,
} from '@lucide/vue'
import { toast } from 'vue-sonner'
import GroupImportSelector from '~/components/GroupImportSelector.vue'
import { usePublications } from '~/composables/usePublications'
import { formatRelativeTime } from '@/lib/utils'
import type { Publication, Subject } from '~/types'

const { list, create, update, remove, duplicate } = usePublications()
const { data: subjects } = await useAPI<Subject[]>('/subjects')
const { currentSubjectId } = useSubjectContext()

const groups = ref<Publication[]>([])
const loading = ref(false)
const sortBy = ref('updated_desc')

const createOpen = ref(false)
const creating = ref(false)
const form = ref<{ title: string; subject_id?: number; description: string }>({
  title: '', subject_id: undefined, description: '',
})

const importOpen = ref(false)
const importGroupId = ref<number | null>(null)

const loadGroups = async () => {
  loading.value = true
  try {
    groups.value = await list({
      pub_type: 'question_group',
      subject_id: currentSubjectId.value,
      sort: sortBy.value,
    })
  } catch {
    toast.error('加载题组失败')
  } finally {
    loading.value = false
  }
}

onMounted(loadGroups)
watch(currentSubjectId, loadGroups)

const onSortChange = () => loadGroups()

const openCreate = () => {
  form.value = { title: '', subject_id: currentSubjectId.value ?? undefined, description: '' }
  createOpen.value = true
}

const submitCreate = async () => {
  if (!form.value.title.trim()) {
    toast.error('请输入题组标题')
    return
  }
  creating.value = true
  try {
    const group = await create({
      title: form.value.title,
      pub_type: 'question_group',
      subject_id: form.value.subject_id ?? null,
      description: form.value.description || null,
    })
    createOpen.value = false
    navigateTo(`/groups/${group.id}/edit`)
  } catch {
    toast.error('创建失败')
  } finally {
    creating.value = false
  }
}

const editGroup = (id: number) => navigateTo(`/groups/${id}/edit`)

const renameGroup = async (group: Publication) => {
  const title = window.prompt('重命名题组', group.title)
  if (!title || title === group.title) return
  try {
    await update(group.id, { title })
    toast.success('已重命名')
    loadGroups()
  } catch {
    toast.error('重命名失败')
  }
}

const duplicateGroup = async (id: number) => {
  try {
    await duplicate(id)
    toast.success('已复制')
    loadGroups()
  } catch {
    toast.error('复制失败')
  }
}

const deleteGroup = async (group: Publication) => {
  if (!window.confirm(`确定删除《${group.title}》吗？此操作不可恢复。`)) return
  try {
    await remove(group.id)
    toast.success('已删除')
    loadGroups()
  } catch {
    toast.error('删除失败')
  }
}

const openImport = (group: Publication) => {
  importGroupId.value = group.id
  importOpen.value = true
}
</script>

<template>
  <PageHeader title="题组">
    <template #actions>
      <Button size="sm" @click="openCreate">
        <Plus class="mr-2 h-4 w-4" />
        新建题组
      </Button>
    </template>
  </PageHeader>

  <div class="flex flex-1 flex-col px-4 py-6 space-y-6">
    <div class="flex items-center justify-end gap-4 flex-wrap">
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
      v-else-if="groups.length > 0"
      class="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
    >
      <Card
        v-for="group in groups"
        :key="group.id"
        class="group hover:shadow-lg transition-shadow cursor-pointer"
        @click="editGroup(group.id)"
      >
        <CardHeader class="pb-3">
          <div class="flex items-start justify-between">
            <Badge variant="outline">
              {{ subjects?.find(s => s.id === group.subject_id)?.name || '未分类' }}
            </Badge>
            <DropdownMenu>
              <DropdownMenuTrigger as-child @click.stop>
                <Button variant="ghost" size="icon" class="h-8 w-8 opacity-0 group-hover:opacity-100">
                  <MoreVertical class="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem @click.stop="renameGroup(group)">
                  <Pencil class="mr-2 h-4 w-4" /> 重命名
                </DropdownMenuItem>
                <DropdownMenuItem @click.stop="duplicateGroup(group.id)">
                  <Copy class="mr-2 h-4 w-4" /> 复制
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem class="text-destructive" @click.stop="deleteGroup(group)">
                  <Trash2 class="mr-2 h-4 w-4" /> 删除
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
          <CardTitle class="mt-2 text-lg line-clamp-1">{{ group.title }}</CardTitle>
          <CardDescription class="line-clamp-2 min-h-[2.5rem]">
            {{ group.description || '暂无描述' }}
          </CardDescription>
        </CardHeader>

        <CardContent>
          <div class="flex items-center gap-4 text-sm text-muted-foreground">
            <div class="flex items-center gap-1">
              <Package class="h-4 w-4" />
              <span>{{ group.block_count }} 项</span>
            </div>
            <div class="flex items-center gap-1">
              <Clock class="h-4 w-4" />
              <span>{{ formatRelativeTime(group.updated_at) }}</span>
            </div>
          </div>
        </CardContent>

        <CardFooter class="pt-3 border-t gap-2">
          <Button variant="outline" class="flex-1" @click.stop="editGroup(group.id)">
            <Edit class="mr-2 h-4 w-4" /> 编辑
          </Button>
          <Button variant="secondary" class="flex-1" @click.stop="openImport(group)">
            <ShoppingBasket class="mr-2 h-4 w-4" /> 加入试题篮
          </Button>
        </CardFooter>
      </Card>
    </div>

    <div v-else class="flex flex-col items-center justify-center py-16 text-center">
      <Package class="h-12 w-12 text-muted-foreground mb-4" />
      <p class="text-muted-foreground mb-4">还没有题组</p>
      <Button @click="openCreate">
        <Plus class="mr-2 h-4 w-4" /> 新建题组
      </Button>
    </div>
  </div>

  <!-- Create dialog -->
  <Dialog v-model:open="createOpen">
    <DialogContent class="sm:max-w-[440px]">
      <DialogHeader>
        <DialogTitle>新建题组</DialogTitle>
      </DialogHeader>
      <div class="space-y-4 py-2">
        <div class="space-y-2">
          <Label>标题</Label>
          <Input v-model="form.title" placeholder="例如：向量数量积-坐标法" autofocus />
        </div>
        <div class="space-y-2">
          <Label>科目</Label>
          <Select v-model="form.subject_id">
            <SelectTrigger>
              <SelectValue placeholder="选择科目" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="s in subjects" :key="s.id" :value="s.id">{{ s.name }}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div class="space-y-2">
          <Label>描述</Label>
          <Textarea v-model="form.description" rows="2" placeholder="可选" />
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

  <GroupImportSelector
    v-model:open="importOpen"
    :group-id="importGroupId"
  />
</template>
