<script setup lang="ts">
import PageHeader from '~/components/PageHeader.vue'
import type { KnowledgePoint, Subject } from '~/types'
import { useAPI } from '~/composables/useAPI'
import { Loader2, Plus, Save, X, Folder } from 'lucide-vue-next'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { toast } from 'vue-sonner'

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

const selectedSubjectId = ref<string>('')

// Initialize selectedSubjectId
if (subjects.value && subjects.value.length > 0) {
  selectedSubjectId.value = String(subjects.value[0].id)
}

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
    toast.success('根目录创建成功')
    
    if (knowledgePoints.value) {
      knowledgePoints.value = [...knowledgePoints.value, newKp]
    } else {
      knowledgePoints.value = [newKp]
    }
    
    newRootName.value = ''
    newRootSlug.value = ''
    isCreatingRoot.value = false
  } catch (e: any) {
    toast.error('创建失败: ' + (e.data?.detail || e.message))
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
    toast.success('子目录创建成功')
    
    if (knowledgePoints.value) {
      knowledgePoints.value = [...knowledgePoints.value, newKp]
    } else {
      knowledgePoints.value = [newKp]
    }
  } catch (e: any) {
    toast.error('创建失败: ' + (e.data?.detail || e.message))
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
    toast.success('更新成功')
    
    if (knowledgePoints.value) {
      const index = knowledgePoints.value.findIndex(k => k.id === id)
      if (index !== -1) {
        const newArr = [...knowledgePoints.value]
        newArr[index] = updatedKp
        knowledgePoints.value = newArr
      }
    }
  } catch (e: any) {
    toast.error('更新失败: ' + (e.data?.detail || e.message))
  }
}

const handleDelete = async (id: number) => {
  if (!confirm('确定要删除该知识点及其所有子知识点吗？')) return

  try {
    await $api(`/knowledge-points/${id}`, {
      method: 'DELETE'
    })
    toast.success('删除成功')
    
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
    toast.error('删除失败: ' + (e.data?.detail || e.message))
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
    toast.success('移动成功')
    
    if (knowledgePoints.value) {
      const index = knowledgePoints.value.findIndex(k => k.id === draggedId)
      if (index !== -1) {
        const newArr = [...knowledgePoints.value]
        newArr[index] = updatedKp
        knowledgePoints.value = newArr
      }
    }
  } catch (e: any) {
    toast.error('移动失败: ' + (e.data?.detail || e.message))
  }
}

// Auto-generate slug
watch(newRootName, (val) => {
  if (!isCreatingRoot.value) return
  newRootSlug.value = val.toLowerCase().replace(/\s+/g, '-')
})
</script>

<template>
  <PageHeader title="知识点管理" description="管理各科目的知识点结构" />

  <div class="flex flex-1 flex-col">
    <div class="@container/main flex flex-1 flex-col px-4 space-y-6 py-6">
      <div v-if="!subjects || subjects.length === 0" class="text-center py-10 text-muted-foreground">
        暂无科目，请先添加科目。
      </div>

      <Tabs v-else v-model="selectedSubjectId" class="w-full">
        <TabsList class="w-full justify-start overflow-x-auto">
          <TabsTrigger v-for="subject in subjects" :key="subject.id" :value="String(subject.id)">
            {{ subject.name }}
          </TabsTrigger>
        </TabsList>

        <div class="mt-4 border rounded-lg p-4 min-h-[500px] bg-card">
          <div class="flex justify-between items-center mb-4">
            <h3 class="text-lg font-medium">知识点树</h3>
            <Button v-if="!isCreatingRoot" size="sm" @click="isCreatingRoot = true">
              <Plus class="w-4 h-4 mr-2" />
              添加根目录
            </Button>
          </div>

          <!-- Root Creation Form -->
          <div v-if="isCreatingRoot" class="mb-4 p-3 border rounded-md bg-muted/30 flex items-center gap-2">
            <div class="mr-2 text-muted-foreground">
              <Folder class="w-4 h-4" />
            </div>
            <Input v-model="newRootName" class="h-8 text-sm w-64" placeholder="根目录名称" />
            <Input v-model="newRootSlug" class="h-8 text-sm w-32" placeholder="Slug" />
            <Button size="sm" class="h-8" @click="handleCreateRoot">
              <Save class="w-4 h-4 mr-2" /> 保存
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
              该科目暂无知识点。
            </div>

            <ManagerKnowledgePointTreeItem v-for="node in knowledgePointTree" :key="node.id" :knowledge-point="node"
              @update="handleUpdate" @delete="handleDelete" @create="handleCreateChild" @move="handleMove" />
          </div>
        </div>
      </Tabs>
    </div>
  </div>
</template>
