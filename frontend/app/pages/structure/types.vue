<script setup lang="ts">
/**
 * 元素类型管理页(规格 §8.3):维护当前学科的条件 / 设问类型树,以及学科的结构化设置。
 *
 * 元素类型由老师确认后生效,不由 AI 决定:AI 拆解时只能从「启用」的类型中选择,选不到时
 * 给出描述(待归类),老师在这里新建、合并类型来吸收它们。
 */
import { computed, onActivated, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import { Download, Loader2, Plus, Search, Upload } from '@lucide/vue'
import PageHeader from '@/components/PageHeader.vue'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import StructTypeTreeItem from '@/components/structure/types/StructTypeTreeItem.vue'
import StructTypeEditDialog from '@/components/structure/types/StructTypeEditDialog.vue'
import StructTypeMoveDialog from '@/components/structure/types/StructTypeMoveDialog.vue'
import StructTypeImportDialog from '@/components/structure/types/StructTypeImportDialog.vue'
import StructCandidatesPanel from '@/components/structure/types/StructCandidatesPanel.vue'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { getApiErrorDetail } from '@/lib/apiErrors'
import {
  buildStructTypeTree,
  filterStructTypeTree,
  type StructTypeFormValue,
  type StructTypeNode,
} from '@/lib/structure'
import type { KnowledgePoint, StructSettings, StructType, StructTypeKind } from '~/types'

const { t } = useI18n()
const api = useStructure()
const { currentSubjectId, currentSubject } = useSubjectContext()
const { refresh: refreshStructureEnabled } = useStructureEnabled()

// region 状态

const types = ref<StructType[]>([])
// 本学科的知识点:编辑类型时用于映射(规格 §12.3 N8)。
const knowledgePoints = ref<KnowledgePoint[]>([])
const { $api } = useNuxtApp()
const settings = ref<StructSettings | null>(null)
const loading = ref(false)
const saving = ref(false)
const search = ref('')

// 新建 / 编辑对话框:editing 为 null 表示新建;newParent 为新建时的上级,newKind 为新建根时的类别。
const editOpen = ref(false)
const editing = ref<StructType | null>(null)
const newParent = ref<StructType | null>(null)
const newKind = ref<StructTypeKind>('condition')

// 移动 / 合并对话框。
const moveOpen = ref(false)
const moveMode = ref<'move' | 'merge'>('move')
const moveSource = ref<StructType | null>(null)

const importOpen = ref(false)

// 存量回填的数量(后端上限 5000)。
// 「类型树」/「待归纳」标签页;从题干结构面板的「待归类」提示跳过来时带 ?tab=candidates。
const route = useRoute()
const tab = ref<'tree' | 'candidates'>(route.query.tab === 'candidates' ? 'candidates' : 'tree')
const candidateCount = ref(0)
const candidatesPanel = ref<InstanceType<typeof StructCandidatesPanel> | null>(null)

const backfillLimit = ref(500)
const backfilling = ref(false)

// endregion

// region 计算属性

const enabled = computed(() => settings.value?.enabled !== false)
const editable = computed(() => enabled.value && !!settings.value?.can_edit_types)
const canManageSubject = computed(() => enabled.value && !!settings.value?.can_manage_subject)

const conditionTree = computed(() => filterStructTypeTree(buildStructTypeTree(types.value, 'condition'), search.value))
const askTree = computed(() => filterStructTypeTree(buildStructTypeTree(types.value, 'ask'), search.value))
const methodTree = computed(() => filterStructTypeTree(buildStructTypeTree(types.value, 'method'), search.value))
const searching = computed(() => !!search.value.trim())

const sections = computed(() => [
  { kind: 'condition' as StructTypeKind, title: t('structure.kinds.condition'), roots: conditionTree.value },
  { kind: 'ask' as StructTypeKind, title: t('structure.kinds.ask'), roots: askTree.value },
  { kind: 'method' as StructTypeKind, title: t('structure.kinds.method'), roots: methodTree.value },
])

// endregion

// region 公共方法 / 事件处理

/** 加载类型树与当前用户在该学科的权限、学科开关。 */
async function load(): Promise<void> {
  const subjectId = currentSubjectId.value
  if (subjectId == null) return
  loading.value = true
  try {
    const [typeList, structureSettings, kps] = await Promise.all([
      api.listTypes(subjectId),
      api.getSettings(subjectId),
      $api<KnowledgePoint[]>('/knowledge-points', { query: { subject_id: subjectId, limit: -1 } }).catch(() => []),
    ])
    knowledgePoints.value = kps
    types.value = typeList.items
    settings.value = structureSettings
  } catch (e) {
    toast.error(t('structure.types.loadFailed'), { description: getApiErrorDetail(e, '') })
  } finally {
    loading.value = false
  }
}

function openCreate(parent: StructType | null, kind: StructTypeKind): void {
  editing.value = null
  newParent.value = parent
  newKind.value = parent?.kind ?? kind
  editOpen.value = true
}

function openEdit(node: StructTypeNode): void {
  editing.value = node
  newParent.value = null
  editOpen.value = true
}

async function submitEdit(value: StructTypeFormValue): Promise<void> {
  const subjectId = currentSubjectId.value
  if (subjectId == null) return
  await run(async () => {
    if (editing.value) {
      await api.updateType(editing.value.id, {
        name: value.name,
        definition: value.definition || null,
        examples: value.examples.length ? value.examples : null,
        status: value.status,
        weight: value.weight,
        knowledge_point_ids: value.knowledge_point_ids,
      })
    } else {
      await api.createType({
        subject_id: subjectId,
        name: value.name,
        code: value.code || undefined,
        kind: newKind.value,
        parent_id: newParent.value?.id ?? null,
        definition: value.definition || null,
        examples: value.examples.length ? value.examples : null,
        status: value.status,
        weight: value.weight,
      })
    }
    editOpen.value = false
    toast.success(t('structure.types.saved'))
  })
}

function openMove(node: StructTypeNode, mode: 'move' | 'merge'): void {
  moveSource.value = node
  moveMode.value = mode
  moveOpen.value = true
}

async function submitMove(targetId: number): Promise<void> {
  const source = moveSource.value
  if (!source) return
  if (moveMode.value === 'merge') {
    // 合并不可撤销:二次确认,并说明会发生什么。
    const target = types.value.find(item => item.id === targetId)
    if (!confirm(t('structure.types.mergeConfirm', { source: source.name, target: target?.name ?? '' }))) return
  }
  await run(async () => {
    if (moveMode.value === 'move') await api.updateType(source.id, { parent_id: targetId })
    else await api.mergeType(source.id, targetId)
    moveOpen.value = false
    toast.success(t(moveMode.value === 'move' ? 'structure.types.moved' : 'structure.types.merged'))
  })
}

async function toggleStatus(node: StructTypeNode): Promise<void> {
  await run(async () => {
    await api.updateType(node.id, { status: node.status === 'active' ? 'deprecated' : 'active' })
  })
}

async function remove(node: StructTypeNode): Promise<void> {
  if (!confirm(t('structure.types.deleteConfirm', { name: node.name }))) return
  // 被引用或有子类型时后端会拒绝,错误提示里会建议改用停用或合并。
  await run(async () => {
    await api.deleteType(node.id)
    toast.success(t('structure.types.deleted'))
  })
}

async function submitImport(items: Array<Record<string, unknown>>): Promise<void> {
  const subjectId = currentSubjectId.value
  if (subjectId == null) return
  await run(async () => {
    const result = await api.importTypes(subjectId, items)
    importOpen.value = false
    toast.success(t('structure.types.imported', { created: result.created, updated: result.updated }))
  })
}

/** 导出为 JSON 文件下载(可再导入到别的学科或环境)。 */
async function exportTypes(): Promise<void> {
  const subjectId = currentSubjectId.value
  if (subjectId == null) return
  try {
    const items = await api.exportTypes(subjectId)
    const blob = new Blob([JSON.stringify(items, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `struct-types-${currentSubject.value?.name ?? subjectId}.json`
    link.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    toast.error(t('structure.types.exportFailed'), { description: getApiErrorDetail(e, '') })
  }
}

async function toggleAutoDecompose(value: boolean): Promise<void> {
  const subjectId = currentSubjectId.value
  if (subjectId == null || !settings.value) return
  try {
    await api.setAutoDecompose(subjectId, value)
    settings.value = { ...settings.value, auto_decompose: value }
    toast.success(t('structure.settings.saved'))
  } catch (e) {
    toast.error(t('common.saveFailed'), { description: getApiErrorDetail(e, '') })
  }
}

async function backfill(): Promise<void> {
  const subjectId = currentSubjectId.value
  if (subjectId == null) return
  // 限制在 1~5000,与后端一致;非数字时用默认值。
  const limit = Math.min(5000, Math.max(1, Math.floor(Number(backfillLimit.value) || 500)))
  backfilling.value = true
  try {
    const result = await api.backfill(subjectId, limit)
    toast.success(t('structure.settings.backfillQueued', { count: result.queued }))
  } catch (e) {
    toast.error(t('structure.settings.backfillFailed'), { description: getApiErrorDetail(e, '') })
  } finally {
    backfilling.value = false
  }
}

// endregion

// region 内部辅助函数

/** 执行一次写操作:统一处理忙碌状态、错误提示与刷新。 */
async function run(action: () => Promise<void>): Promise<void> {
  saving.value = true
  try {
    await action()
    await load()
  } catch (e) {
    toast.error(t('structure.types.actionFailed'), { description: getApiErrorDetail(e, '') })
  } finally {
    saving.value = false
  }
}

// endregion

watch(currentSubjectId, () => { void load() }, { immediate: true })
// 页面 keep-alive:重新进入时刷新(别处可能刚采纳了拆解,引用数会变)。
watch(() => route.query.tab, (value) => {
  if (value === 'candidates') tab.value = 'candidates'
})
onActivated(() => {
  void load()
  void candidatesPanel.value?.load()
  void refreshStructureEnabled()
})
</script>

<template>
  <PageHeader :title="t('nav.structureTypes')" />

  <div class="flex flex-1 flex-col">
    <div class="flex flex-1 flex-col space-y-6 px-4 py-6">
      <p class="text-sm text-muted-foreground">{{ t('structure.types.description') }}</p>

      <p v-if="settings && !enabled" class="rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground">
        {{ t('structure.settings.disabledHint') }}
      </p>

      <!-- 学科设置 -->
      <Card v-if="settings">
        <CardHeader>
          <CardTitle class="text-base">{{ t('structure.settings.subjectTitle', { name: currentSubject?.name ?? '' }) }}</CardTitle>
          <CardDescription>{{ t('structure.settings.subjectDescription') }}</CardDescription>
        </CardHeader>
        <CardContent class="space-y-5">
          <div class="flex items-center justify-between gap-4">
            <div class="space-y-0.5">
              <Label class="text-sm">{{ t('structure.settings.autoLabel') }}</Label>
              <p class="text-sm text-muted-foreground">{{ t('structure.settings.autoHint') }}</p>
            </div>
            <Switch
              :model-value="!!settings.auto_decompose"
              :disabled="!canManageSubject"
              @update:model-value="toggleAutoDecompose"
            />
          </div>
          <div class="flex flex-wrap items-end justify-between gap-4">
            <div class="space-y-0.5">
              <Label class="text-sm">{{ t('structure.settings.backfillLabel') }}</Label>
              <p class="text-sm text-muted-foreground">{{ t('structure.settings.backfillHint') }}</p>
            </div>
            <div class="flex items-center gap-2">
              <Input v-model.number="backfillLimit" type="number" min="1" max="5000" class="h-9 w-24" :disabled="!canManageSubject" />
              <Button variant="outline" :disabled="!canManageSubject || backfilling" @click="backfill">
                <Loader2 v-if="backfilling" class="mr-2 h-4 w-4 animate-spin" />
                {{ t('structure.settings.backfillButton') }}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Tabs v-model="tab" class="space-y-4">
        <TabsList>
          <TabsTrigger value="tree">{{ t('structure.induce.tabTree') }}</TabsTrigger>
          <TabsTrigger value="candidates">
            {{ t('structure.induce.tabCandidates') }}
            <span v-if="candidateCount" class="ml-1.5 rounded-full bg-primary px-1.5 text-xs text-primary-foreground">{{ candidateCount }}</span>
          </TabsTrigger>
        </TabsList>
        <TabsContent value="tree" class="space-y-6">
          <!-- 工具栏 -->
          <div class="flex flex-wrap items-center gap-2">
            <div class="relative w-full max-w-xs">
              <Search class="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input v-model="search" class="h-9 pl-8" :placeholder="t('structure.types.searchPlaceholder')" />
            </div>
            <div class="ml-auto flex flex-wrap gap-2">
              <Button variant="outline" size="sm" @click="exportTypes"><Download class="mr-2 h-4 w-4" />{{ t('structure.types.export') }}</Button>
              <Button v-if="editable" variant="outline" size="sm" @click="importOpen = true"><Upload class="mr-2 h-4 w-4" />{{ t('structure.types.import') }}</Button>
            </div>
          </div>

          <div v-if="loading && !types.length" class="flex items-center gap-2 py-10 text-sm text-muted-foreground">
            <Loader2 class="h-4 w-4 animate-spin" /> {{ t('common.loading') }}
          </div>

          <!-- 条件类型 / 设问类型两棵树 -->
          <div v-else class="grid gap-6 xl:grid-cols-2">
            <section v-for="section in sections" :key="section.kind" class="rounded-lg border bg-card p-3">
              <div class="mb-2 flex items-center justify-between px-2">
                <h3 class="font-medium">{{ section.title }}</h3>
                <Button v-if="editable" size="sm" variant="ghost" class="h-7" @click="openCreate(null, section.kind)">
                  <Plus class="mr-1 h-4 w-4" />{{ t('structure.types.addRoot') }}
                </Button>
              </div>
              <StructTypeTreeItem
                v-for="node in section.roots"
                :key="node.id"
                :node="node"
                :types="types"
                :editable="editable"
                :force-open="searching"
                @add-child="openCreate($event, section.kind)"
                @edit="openEdit"
                @move="openMove($event, 'move')"
                @merge="openMove($event, 'merge')"
                @toggle-status="toggleStatus"
                @delete="remove"
              />
              <p v-if="!section.roots.length" class="px-2 py-4 text-sm text-muted-foreground">
                {{ searching ? t('structure.typeSelect.empty') : t('structure.types.empty') }}
              </p>
            </section>
          </div>
        </TabsContent>
        <TabsContent value="candidates" :force-mount="true" :hidden="tab !== 'candidates'">
          <StructCandidatesPanel
            ref="candidatesPanel"
            :subject-id="currentSubjectId ?? null"
            :types="types"
            :editable="editable"
            :can-induce="canManageSubject"
            @changed="load"
            @count="candidateCount = $event"
          />
        </TabsContent>
      </Tabs>
    </div>
  </div>

  <StructTypeEditDialog
    v-model:open="editOpen"
    :initial="editing"
    :parent-name="newParent?.name ?? null"
    :saving="saving"
    :kind="editing?.kind ?? newKind"
    :knowledge-points="knowledgePoints"
    @submit="submitEdit"
  />
  <StructTypeMoveDialog
    v-model:open="moveOpen"
    :mode="moveMode"
    :source="moveSource"
    :types="types"
    :saving="saving"
    @submit="submitMove"
  />
  <StructTypeImportDialog v-model:open="importOpen" :saving="saving" @submit="submitImport" />
</template>
