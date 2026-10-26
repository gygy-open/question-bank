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
import { Plus, Pencil, Trash2, Users } from '@lucide/vue'
import SubjectMembersDialog from '~/components/manager/SubjectMembersDialog.vue'

// State
const { t } = useI18n()
const { $api } = useNuxtApp()
const { data: subjects, refresh } = await useAPI<Subject[]>('/api/v1/subjects')
const { refreshSubjects } = useSubjectContext()
const isDialogOpen = ref(false)
const isEditing = ref(false)
const membersDialogOpen = ref(false)
const membersSubject = ref<Subject | null>(null)
const currentSubject = ref<Partial<Subject>>({
  name: '',
  slug: '',
  description: '',
  required_review_count: 1
})

const openMembersDialog = (subject: Subject) => {
  membersSubject.value = subject
  membersDialogOpen.value = true
}

const { can, isAdmin } = usePermissions()
const canManageMembers = (subjectId: number) => can(Capability.MANAGE_MEMBERS, subjectId)

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
    await refreshSubjects()
    isDialogOpen.value = false
  } catch (error) {
    console.error('Failed to save subject', error)
  }
}

const deleteSubject = async (id: number) => {
  if (!confirm(t('subjects.deleteConfirmWithImpact'))) return
  try {
    await $api(`/api/v1/subjects/${id}`, { method: 'DELETE' })
    await refresh()
    await refreshSubjects()
  } catch (error) {
    console.error('Failed to delete subject', error)
  }
}
</script>

<template>
  <PageHeader :title="t('nav.subjects')">
    <template #actions>
      <Button v-if="isAdmin" @click="openCreateDialog">
        <Plus class="w-4 h-4 mr-2" />
        {{ t('subjects.createNew') }}
      </Button>
    </template>
  </PageHeader>

  <div class="flex-1 overflow-auto">
    <div class="max-w-7xl mx-auto p-6">
      <!-- 表格卡片 -->
      <div class="bg-card text-card-foreground rounded-lg shadow-sm border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>ID</TableHead>
              <TableHead>{{ t('common.name') }}</TableHead>
              <TableHead>{{ t('subjects.slugLabel') }}</TableHead>
              <TableHead>{{ t('subjects.requiredReviewCount') }}</TableHead>
              <TableHead>{{ t('subjects.description') }}</TableHead>
              <TableHead class="text-right">{{ t('common.actions') }}</TableHead>
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
                  <Button v-if="canManageMembers(subject.id)" variant="ghost" size="icon" :title="t('subjects.members')" @click="openMembersDialog(subject)">
                    <Users class="w-4 h-4" />
                  </Button>
                  <Button v-if="isAdmin" variant="ghost" size="icon" @click="openEditDialog(subject)">
                    <Pencil class="w-4 h-4" />
                  </Button>
                  <Button v-if="isAdmin" variant="ghost" size="icon" class="text-destructive" @click="deleteSubject(subject.id)">
                    <Trash2 class="w-4 h-4" />
                  </Button>
                </div>
              </TableCell>
            </TableRow>
            <TableRow v-if="!subjects || subjects.length === 0">
              <TableCell colspan="6" class="text-center py-8 text-muted-foreground">
                {{ t('subjects.empty') }}
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </div>
    </div>
  </div>

  <!-- 对话框 -->
  <Dialog v-model:open="isDialogOpen">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{{ isEditing ? t('subjects.edit') : t('subjects.createNew') }}</DialogTitle>
          <DialogDescription>
            {{ t('subjects.dialogDescription') }}
          </DialogDescription>
        </DialogHeader>
        
        <div class="grid gap-4 py-4">
          <div class="grid gap-2">
            <label>{{ t('common.name') }}</label>
            <Input v-model="currentSubject.name" :placeholder="t('subjects.namePlaceholderFull')" />
          </div>
          
          <div class="grid gap-2">
            <label>{{ t('subjects.slugLabel') }}</label>
            <Input v-model="currentSubject.slug" :placeholder="t('subjects.slugPlaceholderFull')" />
            <p class="text-xs text-muted-foreground">{{ t('subjects.slugHint') }}</p>
          </div>

          <div class="grid gap-2">
            <label>{{ t('subjects.description') }}</label>
            <Input v-model="currentSubject.description" :placeholder="t('subjects.descriptionPlaceholderOptional')" />
          </div>

          <div class="grid gap-2">
            <label>{{ t('subjects.requiredReviewCount') }}</label>
            <Input v-model="currentSubject.required_review_count" type="number" min="1" />
            <p class="text-xs text-muted-foreground">{{ t('subjects.requiredReviewHint') }}</p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" @click="isDialogOpen = false">{{ t('common.cancel') }}</Button>
          <Button @click="saveSubject">{{ t('common.save') }}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <SubjectMembersDialog v-model:open="membersDialogOpen" :subject="membersSubject" />
</template>
