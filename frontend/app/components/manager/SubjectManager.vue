<script setup lang="ts">
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import * as z from 'zod'
import type { Subject } from '~/types'
import { useAPI } from '~/composables/useAPI'
import { Loader2, Edit, Trash2 } from 'lucide-vue-next'

const { $api } = useNuxtApp()

// --- State ---
const isDialogOpen = ref(false)
const isEditing = ref(false)
const currentId = ref<number | null>(null)

// --- Data Fetching ---
const { data: subjects, refresh, status } = await useAPI<Subject[]>('/subjects')

// --- Form Validation ---
const formSchema = toTypedSchema(z.object({
  name: z.string().min(2, '名称至少2个字符').max(50, '名称最多50个字符'),
  slug: z.string().min(2, '标识至少2个字符').max(50, '标识最多50个字符'),
  description: z.string().optional(),
}))

const form = useForm({
  validationSchema: formSchema,
})

// --- Actions ---
const onSubmit = form.handleSubmit(async (values) => {
  try {
    if (isEditing.value && currentId.value) {
      await $api(`/subjects/${currentId.value}`, {
        method: 'PUT',
        body: values,
      })
    } else {
      await $api('/subjects', {
        method: 'POST',
        body: values,
      })
    }
    isDialogOpen.value = false
    refresh()
    form.resetForm()
  } catch (error) {
    console.error(error)
  }
})

const openCreateDialog = () => {
  isEditing.value = false
  currentId.value = null
  form.resetForm()
  isDialogOpen.value = true
}

const openEditDialog = (subject: Subject) => {
  isEditing.value = true
  currentId.value = subject.id
  form.setValues({
    name: subject.name,
    slug: subject.slug,
    description: subject.description,
  })
  isDialogOpen.value = true
}

const deleteSubject = async (id: number) => {
  if (!confirm('确定要删除这个科目吗？')) return
  try {
    await $api(`/subjects/${id}`, {
      method: 'DELETE',
    })
    refresh()
  } catch (error) {
    console.error(error)
  }
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <h3 class="text-lg font-medium">科目列表</h3>
      <Button @click="openCreateDialog" size="sm">创建科目</Button>
    </div>

    <div class="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>名称</TableHead>
            <TableHead>标识</TableHead>
            <TableHead>描述</TableHead>
            <TableHead class="text-right">操作</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow v-if="status === 'pending'">
            <TableCell colspan="4" class="h-24 text-center">
              <Loader2 class="h-6 w-6 animate-spin mx-auto" />
            </TableCell>
          </TableRow>
          <TableRow v-else-if="subjects?.length === 0">
            <TableCell colspan="4" class="h-24 text-center">
              暂无数据
            </TableCell>
          </TableRow>
          <TableRow v-for="subject in subjects" :key="subject.id">
            <TableCell class="font-medium">{{ subject.name }}</TableCell>
            <TableCell>{{ subject.slug }}</TableCell>
            <TableCell>{{ subject.description }}</TableCell>
            <TableCell class="text-right">
              <Button variant="ghost" size="icon" @click="openEditDialog(subject)">
                <Edit class="h-4 w-4" />
              </Button>
              <Button variant="ghost" size="icon" class="text-destructive" @click="deleteSubject(subject.id)">
                <Trash2 class="h-4 w-4" />
              </Button>
            </TableCell>>
          </TableRow>
        </TableBody>
      </Table>
    </div>

    <Dialog :open="isDialogOpen" @update:open="isDialogOpen = $event">
      <DialogContent class="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>{{ isEditing ? '编辑科目' : '创建科目' }}</DialogTitle>
          <DialogDescription>
            {{ isEditing ? '修改科目信息' : '添加一个新的科目' }}
          </DialogDescription>
        </DialogHeader>
        <form @submit="onSubmit" class="space-y-4">
          <FormField v-slot="{ componentField }" name="name">
            <FormItem>
              <FormLabel>名称</FormLabel>
              <FormControl>
                <Input type="text" placeholder="例如：数学" v-bind="componentField" />
              </FormControl>
              <FormMessage />
            </FormItem>
          </FormField>

          <FormField v-slot="{ componentField }" name="slug">
            <FormItem>
              <FormLabel>标识 (Slug)</FormLabel>
              <FormControl>
                <Input type="text" placeholder="例如：math" v-bind="componentField" />
              </FormControl>
              <FormMessage />
            </FormItem>
          </FormField>

          <FormField v-slot="{ componentField }" name="description">
            <FormItem>
              <FormLabel>描述</FormLabel>
              <FormControl>
                <Textarea placeholder="科目描述..." v-bind="componentField" />
              </FormControl>
              <FormMessage />
            </FormItem>
          </FormField>

          <DialogFooter>
            <Button type="submit">保存</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  </div>
</template>