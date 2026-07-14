<script setup lang="ts">
import { ref } from 'vue'
import { useAPI } from '~/composables/useAPI'
import type { Subject } from '~/types'
import PageHeader from '~/components/PageHeader.vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Plus, Pencil, Trash2 } from 'lucide-vue-next'

// State
const { $api } = useNuxtApp()
const { data: subjects, refresh } = await useAPI<Subject[]>('/api/v1/subjects')
const isDialogOpen = ref(false)
const isEditing = ref(false)
const currentSubject = ref<Partial<Subject>>({
  name: '',
  slug: '',
  description: '',
  required_review_count: 1
})

// Actions
const openCreateDialog = () => {
  isEditing.value = false
  currentSubject.value = { name: '', slug: '', description: '', required_review_count: 1 }
  isDialogOpen.value = true
}

const openEditDialog = (subject: Subject) => {
  isEditing.value = true
  currentSubject.value = { ...subject }
  isDialogOpen.value = true
}

const saveSubject = async () => {
  try {
    if (isEditing.value && currentSubject.value.id) {
      await $api(`/api/v1/subjects/${currentSubject.value.id}`, {
        method: 'PUT',
        body: currentSubject.value
      })
    } else {
      await $api('/api/v1/subjects', {
        method: 'POST',
        body: currentSubject.value
      })
    }
    await refresh()
    isDialogOpen.value = false
  } catch (error) {
    console.error('Failed to save subject', error)
  }
}

const deleteSubject = async (id: number) => {
  if (!confirm('确定要删除这个科目吗？删除科目可能会影响关联的题目和目录。')) return
  try {
    await $api(`/api/v1/subjects/${id}`, { method: 'DELETE' })
    await refresh()
  } catch (error) {
    console.error('Failed to delete subject', error)
  }
}
</script>

<template>
  <PageHeader title="科目管理">
    <template #actions>
      <Button @click="openCreateDialog">
        <Plus class="w-4 h-4 mr-2" />
        新建科目
      </Button>
    </template>
  </PageHeader>

  <div class="flex flex-1 flex-col">
    <div class="@container/main flex flex-1 flex-col px-4 space-y-6 py-6">
      <div class="border rounded-md">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>ID</TableHead>
              <TableHead>名称</TableHead>
              <TableHead>标识 (Slug)</TableHead>
              <TableHead>所需审核次数</TableHead>
              <TableHead>描述</TableHead>
              <TableHead class="text-right">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow v-for="subject in subjects" :key="subject.id">
              <TableCell>{{ subject.id }}</TableCell>
              <TableCell class="font-medium">{{ subject.name }}</TableCell>
              <TableCell>{{ subject.slug }}</TableCell>
              <TableCell>{{ subject.required_review_count }}</TableCell>
              <TableCell class="text-muted-foreground">{{ subject.description || '-' }}</TableCell>
              <TableCell class="text-right">
                <div class="flex justify-end gap-2">
                  <Button variant="ghost" size="icon" @click="openEditDialog(subject)">
                    <Pencil class="w-4 h-4" />
                  </Button>
                  <Button variant="ghost" size="icon" class="text-destructive" @click="deleteSubject(subject.id)">
                    <Trash2 class="w-4 h-4" />
                  </Button>
                </div>
              </TableCell>
            </TableRow>
            <TableRow v-if="!subjects || subjects.length === 0">
              <TableCell colspan="5" class="text-center py-8 text-muted-foreground">
                暂无科目
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </div>
    </div>

    <Dialog v-model:open="isDialogOpen">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{{ isEditing ? '编辑科目' : '新建科目' }}</DialogTitle>
          <DialogDescription>
            配置科目的基本信息。
          </DialogDescription>
        </DialogHeader>
        
        <div class="grid gap-4 py-4">
          <div class="grid gap-2">
            <label>名称</label>
            <Input v-model="currentSubject.name" placeholder="例如：高中数学" />
          </div>
          
          <div class="grid gap-2">
            <label>标识 (Slug)</label>
            <Input v-model="currentSubject.slug" placeholder="例如：math-hs" />
            <p class="text-xs text-muted-foreground">用于 URL 和系统内部标识，建议使用英文。</p>
          </div>

          <div class="grid gap-2">
            <label>描述</label>
            <Input v-model="currentSubject.description" placeholder="可选：科目的详细描述" />
          </div>

          <div class="grid gap-2">
            <label>所需审核次数</label>
            <Input v-model="currentSubject.required_review_count" type="number" min="1" />
            <p class="text-xs text-muted-foreground">题目发布前需要经过的审核次数。</p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" @click="isDialogOpen = false">取消</Button>
          <Button @click="saveSubject">保存</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
