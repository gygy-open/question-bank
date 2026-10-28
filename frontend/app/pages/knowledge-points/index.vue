<script setup lang="ts">
import PageHeader from '~/components/PageHeader.vue'
import type { KnowledgePoint, Subject, VectorStatus, ReindexResult } from '~/types'
import { useAPI } from '~/composables/useAPI'
import { Loader2, Plus, Save, X, Folder, Upload, Download, RefreshCw, Database } from '@lucide/vue'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import KnowledgePointImportDialog from '@/components/manager/KnowledgePointImportDialog.vue'
import { toast } from 'vue-sonner'

const { t } = useI18n()
const { $api } = useNuxtApp()

// --- Types ---
interface KnowledgePointNode extends KnowledgePoint {
  children: KnowledgePointNode[]
}

// --- State ---
const isCreatingRoot = ref(false)
const newRootName = ref('')
const newRootSlug = ref('')

// --- Data Fetching ---
const { data: subjects } = await useAPI<Subject[]>('/subjects')
const { data: currentUser } = await useAPI<{ is_superuser?: boolean }>('/users/me')
const isSuperuser = computed(() => !!currentUser.value?.is_superuser)

// Subject is driven by the global subject context (sidebar selector).
const { currentSubjectId, setSubject } = useSubjectContext()
const { can } = usePermissions()
const canManage = computed(() => can(Capability.EDIT_TAXONOMY, currentSubjectId.value))
const selectedSubjectId = computed<string>({
  get: () => (currentSubjectId.value != null ? String(currentSubjectId.value) : ''),
  set: (val) => {
    if (val) setSubject(Number(val)).catch(() => {})
  },
})

const selectedSubjectName = computed(() =>
  subjects.value?.find(s => String(s.id) === selectedSubjectId.value)?.name || ''
)

const { data: knowledgePoints, refresh, status } = await useAPI<KnowledgePoint[]>('/knowledge-points', {
  query: computed(() => ({ subject_id: selectedSubjectId.value, limit: -1 })),
  watch: [selectedSubjectId]
})

// --- Tree Logic ---
const knowledgePointTree = computed<KnowledgePointNode[]>(() => {
  if (!knowledgePoints.value) return []

  const map = new Map<number, KnowledgePointNode>()
  const roots: KnowledgePointNode[] = []

  // Initialize map with clones to avoid mutating original data
  knowledgePoints.value.forEach(kp => {
    map.set(kp.id, { ...kp, children: [] })
  })

  // Build tree
  knowledgePoints.value.forEach(kp => {
    const node = map.get(kp.id)!
    if (kp.parent_id) {
      const parent = map.get(kp.parent_id)
      if (parent) {
        parent.children.push(node)
      } else {
        // Orphaned or parent not in current set (shouldn't happen with correct data)
        roots.push(node)
      }
    } else {
      roots.push(node)
    }
  })

  return roots
})

// --- Actions ---

const handleCreateRoot = async () => {
  if (!newRootName.value.trim() || !newRootSlug.value.trim()) return

  try {
    const newKp = await $api<KnowledgePoint>('/knowledge-points', {
      method: 'POST',
      body: {
        name: newRootName.value,
        slug: newRootSlug.value,
        subject_id: Number(selectedSubjectId.value),
        parent_id: null
      }
    })
    toast.success(t('kpManager.toast.rootCreated'))
    
    if (knowledgePoints.value) {
      knowledgePoints.value = [...knowledgePoints.value, newKp]
    } else {
      knowledgePoints.value = [newKp]
    }
    
    newRootName.value = ''
    newRootSlug.value = ''
    isCreatingRoot.value = false
  } catch (e: any) {
    toast.error(t('kpManager.toast.createFailed', { error: e.data?.detail || e.message }))
  }
}

const handleCreateChild = async (parentId: number, data: { name: string, slug: string }) => {
  try {
    const newKp = await $api<KnowledgePoint>('/knowledge-points', {
      method: 'POST',
      body: {
        name: data.name,
        slug: data.slug,
        subject_id: Number(selectedSubjectId.value),
        parent_id: parentId
      }
    })
    toast.success(t('kpManager.toast.childCreated'))
    
    if (knowledgePoints.value) {
      knowledgePoints.value = [...knowledgePoints.value, newKp]
    } else {
      knowledgePoints.value = [newKp]
    }
  } catch (e: any) {
    toast.error(t('kpManager.toast.createFailed', { error: e.data?.detail || e.message }))
  }
}

const handleUpdate = async (id: number, data: { name: string, slug: string }) => {
  try {
    const updatedKp = await $api<KnowledgePoint>(`/knowledge-points/${id}`, {
      method: 'PUT',
      body: {
        name: data.name,
        slug: data.slug
      }
    })
    toast.success(t('kpManager.toast.updated'))
    
    if (knowledgePoints.value) {
      const index = knowledgePoints.value.findIndex(k => k.id === id)
      if (index !== -1) {
        const newArr = [...knowledgePoints.value]
        newArr[index] = updatedKp
        knowledgePoints.value = newArr
      }
    }
  } catch (e: any) {
    toast.error(t('kpManager.toast.updateFailed', { error: e.data?.detail || e.message }))
  }
}

const handleDelete = async (id: number) => {
  if (!confirm(t('kpManager.deleteConfirm'))) return

  try {
    await $api(`/knowledge-points/${id}`, {
      method: 'DELETE'
    })
    toast.success(t('kpManager.toast.deleted'))
    
    if (knowledgePoints.value) {
      // Recursive deletion logic might be needed if the backend deletes children but we only remove the parent from the flat list.
      // However, since we rebuild the tree from the flat list, removing the parent is enough to remove the subtree from the view.
      // But to be clean, we should probably remove children too if we want to keep the flat list in sync with DB.
      // The backend likely cascades deletes.
      // For the UI, removing the node is sufficient as its children won't be attached to anything in the tree builder if we don't remove them, 
      // OR they will become roots if we don't remove them and the tree builder logic handles orphans.
      // The tree builder logic:
      // if (parent) parent.children.push(node) else roots.push(node)
      // So if we delete a parent but not children in the flat list, the children will become roots!
      // So we MUST remove children from the flat list as well.
      
      // Helper to find all descendants
      const toDelete = new Set<number>()
      toDelete.add(id)
      
      let added = true
      while (added) {
        added = false
        knowledgePoints.value.forEach(kp => {
          if (kp.parent_id && toDelete.has(kp.parent_id) && !toDelete.has(kp.id)) {
            toDelete.add(kp.id)
            added = true
          }
        })
      }
      
      knowledgePoints.value = knowledgePoints.value.filter(k => !toDelete.has(k.id))
    }
  } catch (e: any) {
    toast.error(t('kpManager.toast.deleteFailed', { error: e.data?.detail || e.message }))
  }
}

const handleMove = async (draggedId: number, targetId: number) => {
  // Simple implementation: just update parent_id
  // Backend should handle cycle detection ideally
  try {
    const updatedKp = await $api<KnowledgePoint>(`/knowledge-points/${draggedId}`, {
      method: 'PUT',
      body: {
        parent_id: targetId
      }
    })
    toast.success(t('kpManager.toast.moved'))
    
    if (knowledgePoints.value) {
      const index = knowledgePoints.value.findIndex(k => k.id === draggedId)
      if (index !== -1) {
        const newArr = [...knowledgePoints.value]
        newArr[index] = updatedKp
        knowledgePoints.value = newArr
      }
    }
  } catch (e: any) {
    toast.error(t('kpManager.toast.moveFailed', { error: e.data?.detail || e.message }))
  }
}

// Auto-generate slug
watch(newRootName, (val) => {
  if (!isCreatingRoot.value) return
  newRootSlug.value = val.toLowerCase().replace(/\s+/g, '-')
})

// --- Batch import & vector sync ---
const showImportDialog = ref(false)
const vectorStatus = ref<VectorStatus | null>(null)
const vectorReason = computed(() =>
  vectorStatus.value
    ? t(`kpManager.vector.reason.${vectorStatus.value.reason_code}`, { count: vectorStatus.value.count })
    : '',
)
const isReindexing = ref(false)

const fetchVectorStatus = async () => {
  if (!isSuperuser.value) return
  try {
    vectorStatus.value = await $api<VectorStatus>('/knowledge-points/vector-status')
  } catch {
    vectorStatus.value = null
  }
}

const handleImported = async () => {
  await refresh()
  await fetchVectorStatus()
}

const handleReindex = async () => {
  isReindexing.value = true
  try {
    const res = await $api<ReindexResult>('/knowledge-points/reindex-vectors', { method: 'POST' })
    toast.success(t('kpManager.toast.reindexed', { count: res.reindexed, duration: res.duration }))
    await fetchVectorStatus()
  } catch (e: any) {
    toast.error(t('kpManager.toast.reindexFailed', { error: e.data?.detail || e.message }))
  } finally {
    isReindexing.value = false
  }
}

onMounted(fetchVectorStatus)
</script>

<template>
  <PageHeader :title="t('nav.knowledgePoints')" :description="t('kpManager.pageDescription')" />

  <div class="flex flex-1 flex-col">
    <div class="@container/main flex flex-1 flex-col px-4 space-y-6 py-6">
      <div v-if="!subjects || subjects.length === 0" class="text-center py-10 text-muted-foreground">
        {{ t('kpManager.noSubjects') }}
      </div>

      <Tabs v-else v-model="selectedSubjectId" class="w-full">
        <div class="mt-4 border rounded-lg p-4 min-h-[500px] bg-card">
          <div class="flex justify-between items-center mb-4 gap-2 flex-wrap">
            <h3 class="text-lg font-medium">{{ t('kpManager.treeTitle') }}</h3>
            <div class="flex items-center gap-2">
              <template v-if="isSuperuser">
                <Button variant="outline" size="sm" @click="showImportDialog = true">
                  <Upload class="w-4 h-4 mr-2" />{{ t('kpManager.batchImport') }}
                </Button>
              </template>
              <Button v-if="canManage && !isCreatingRoot" size="sm" @click="isCreatingRoot = true">
                <Plus class="w-4 h-4 mr-2" />
                {{ t('kpManager.addRoot') }}
              </Button>
            </div>
          </div>

          <!-- Vector index status (superuser only, only when reindex needed) -->
          <Alert v-if="isSuperuser && vectorStatus && !vectorStatus.embedding_configured" class="mb-4 items-center [&>svg]:translate-y-0">
            <Database class="h-4 w-4" />
            <AlertDescription class="flex items-center justify-between gap-2">
              <span class="text-sm">{{ t('kpManager.vector.notConfigured', { reason: vectorReason }) }}</span>
              <Button size="sm" variant="outline" as-child>
                <NuxtLink to="/settings">{{ t('kpManager.vector.goToSettings') }}</NuxtLink>
              </Button>
            </AlertDescription>
          </Alert>
          <Alert v-else-if="isSuperuser && vectorStatus?.needs_reindex" class="mb-4 items-center [&>svg]:translate-y-0">
            <Database class="h-4 w-4" />
            <AlertDescription class="flex items-center justify-between gap-2">
              <span class="text-sm">{{ t('kpManager.vector.needsReindex', { reason: vectorReason }) }}</span>
              <Button size="sm" variant="outline" :disabled="isReindexing" @click="handleReindex">
                <RefreshCw class="w-4 h-4 mr-2" :class="{ 'animate-spin': isReindexing }" />
                {{ t('kpManager.vector.reindex') }}
              </Button>
            </AlertDescription>
          </Alert>

          <!-- Root Creation Form -->
          <div v-if="isCreatingRoot" class="mb-4 p-3 border rounded-md bg-muted/30 flex items-center gap-2">
            <div class="mr-2 text-muted-foreground">
              <Folder class="w-4 h-4" />
            </div>
            <Input v-model="newRootName" class="h-8 text-sm w-64" :placeholder="t('kpManager.rootNamePlaceholder')" />
            <Input v-model="newRootSlug" class="h-8 text-sm w-32" placeholder="Slug" />
            <Button size="sm" class="h-8" @click="handleCreateRoot">
              <Save class="w-4 h-4 mr-2" /> {{ t('common.save') }}
            </Button>
            <Button size="sm" variant="ghost" class="h-8" @click="isCreatingRoot = false">
              <X class="w-4 h-4" />
            </Button>
          </div>

          <!-- Loading State -->
          <div v-if="status === 'pending'" class="flex justify-center py-10">
            <Loader2 class="w-8 h-8 animate-spin text-muted-foreground" />
          </div>

          <!-- Tree View -->
          <div v-else class="space-y-1">
            <div v-if="knowledgePointTree.length === 0" class="text-center py-10 text-muted-foreground">
              {{ t('kpManager.empty') }}
            </div>

            <ManagerKnowledgePointTreeItem v-for="node in knowledgePointTree" :key="node.id" :knowledge-point="node" :editable="canManage"
              @update="handleUpdate" @delete="handleDelete" @create="handleCreateChild" @move="handleMove" />
          </div>
        </div>
      </Tabs>
    </div>

    <KnowledgePointImportDialog
      v-model:open="showImportDialog"
      :subject-id="selectedSubjectId ? Number(selectedSubjectId) : null"
      :subject-name="selectedSubjectName"
      @imported="handleImported"
    />
  </div>
</template>
