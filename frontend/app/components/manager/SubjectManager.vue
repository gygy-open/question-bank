<script setup lang="ts">
import { useForm } from 'vee-validate'
import { toTypedSchema } from '@vee-validate/zod'
import * as z from 'zod'
import type { Subject } from '~/types'
import { useAPI } from '~/composables/useAPI'
import { Loader2, Edit, Trash2 } from '@lucide/vue'

const { t } = useI18n()
const { $api } = useNuxtApp()

// --- State ---
const isDialogOpen = ref(false)
const isEditing = ref(false)
const currentId = ref<number | null>(null)

// --- Data Fetching ---
const { data: subjects, refresh, status } = await useAPI<Subject[]>('/subjects')

// --- Form Validation ---
const formSchema = computed(() => toTypedSchema(z.object({
  name: z.string().min(2, t('subjects.validation.nameMin')).max(50, t('subjects.validation.nameMax')),
  slug: z.string().min(2, t('subjects.validation.slugMin')).max(50, t('subjects.validation.slugMax')),
  description: z.string().optional(),
})))

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
  if (!confirm(t('subjects.deleteConfirm'))) return
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
      <h3 class="text-lg font-medium">{{ t('subjects.listTitle') }}</h3>
      <Button @click="openCreateDialog" size="sm">{{ t('subjects.create') }}</Button>
    </div>

    <div class="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{{ t('common.name') }}</TableHead>
            <TableHead>{{ t('subjects.slug') }}</TableHead>
            <TableHead>{{ t('subjects.description') }}</TableHead>
            <TableHead class="text-right">{{ t('common.actions') }}</TableHead>
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
              {{ t('common.noData') }}
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
          <DialogTitle>{{ isEditing ? t('subjects.edit') : t('subjects.create') }}</DialogTitle>
          <DialogDescription>
            {{ isEditing ? t('subjects.editDescription') : t('subjects.createDescription') }}
          </DialogDescription>
        </DialogHeader>
        <form @submit="onSubmit" class="space-y-4">
          <FormField v-slot="{ componentField }" name="name">
            <FormItem>
              <FormLabel>{{ t('common.name') }}</FormLabel>
              <FormControl>
                <Input type="text" :placeholder="t('subjects.namePlaceholder')" v-bind="componentField" />
              </FormControl>
              <FormMessage />
            </FormItem>
          </FormField>

          <FormField v-slot="{ componentField }" name="slug">
            <FormItem>
              <FormLabel>{{ t('subjects.slugLabel') }}</FormLabel>
              <FormControl>
                <Input type="text" :placeholder="t('subjects.slugPlaceholder')" v-bind="componentField" />
              </FormControl>
              <FormMessage />
            </FormItem>
          </FormField>

          <FormField v-slot="{ componentField }" name="description">
            <FormItem>
              <FormLabel>{{ t('subjects.description') }}</FormLabel>
              <FormControl>
                <Textarea :placeholder="t('subjects.descriptionPlaceholder')" v-bind="componentField" />
              </FormControl>
              <FormMessage />
            </FormItem>
          </FormField>

          <DialogFooter>
            <Button type="submit">{{ t('common.save') }}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  </div>
</template>