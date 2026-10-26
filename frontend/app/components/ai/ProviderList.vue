<script setup lang="ts">
import { Image as ImageIcon, KeyRound, Link2, Loader2, MoreHorizontal, Pencil, Plus, Search, Trash2, User } from '@lucide/vue'
import { toast } from 'vue-sonner'
import type { AIConfigScope, AIModel, AIModelInput, AIProvider, InterfaceType } from '~/types/ai-config'
import { INTERFACE_LABEL_KEYS } from '~/lib/ai-config'
import ConfirmDialog from '~/components/ai/ConfirmDialog.vue'
import ModelPicker from '~/components/ai/ModelPicker.vue'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Checkbox } from '@/components/ui/checkbox'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

const { t } = useI18n()

const props = withDefaults(defineProps<{
  providers: AIProvider[]
  scope: AIConfigScope
  /** modelId → 正在使用它的场景 */
  usage?: Map<number, string[]>
  /** 管理员审查他人个人服务商：只读，仅可删除 */
  review?: boolean
}>(), { usage: () => new Map(), review: false })

const emit = defineEmits<{ changed: [] }>()

const api = useAIConfigApi(props.review ? 'global' : props.scope)
const confirmRef = ref<InstanceType<typeof ConfirmDialog> | null>(null)
const ask = (opts: Parameters<NonNullable<typeof confirmRef.value>['ask']>[0]) =>
  confirmRef.value?.ask(opts) ?? Promise.resolve('cancel' as const)

const providerUsage = (p: AIProvider) =>
  [...new Set(p.models.flatMap(m => props.usage.get(m.id) ?? []))]

// ---- 删除（被全局场景引用时二次确认，force 清空引用） ----
const deleteWithForce = async (run: (force: boolean) => Promise<unknown>) => {
  try {
    await run(false)
    return true
  } catch (e) {
    if (apiErrorStatus(e) !== 409) throw e
    const r = await ask({
      title: t('aiProviders.inUse.title'),
      description: t('aiProviders.inUse.description', { error: apiErrorMessage(e) }),
      confirmLabel: t('aiProviders.inUse.confirm'),
      destructive: true,
    })
    if (r !== 'confirm') return false
    await run(true)
    return true
  }
}

const removeProvider = async (p: AIProvider) => {
  const r = await ask({
    title: props.review && p.owner_name
      ? t('aiProviders.deleteProvider.titleWithOwner', { name: p.name, owner: p.owner_name })
      : t('aiProviders.deleteProvider.title', { name: p.name }),
    description: t('aiProviders.deleteProvider.description', { count: p.models.length }),
    confirmLabel: t('common.delete'),
    destructive: true,
  })
  if (r !== 'confirm') return
  try {
    if (await deleteWithForce(force => api.deleteProvider(p.id, force))) {
      toast.success(t('aiProviders.toast.providerDeleted'))
      emit('changed')
    }
  } catch (e) {
    toast.error(t('common.deleteFailed'), { description: apiErrorMessage(e) })
  }
}

const removeModel = async (m: AIModel) => {
  const r = await ask({ title: t('aiProviders.deleteModel.title', { name: m.name }), confirmLabel: t('common.delete'), destructive: true })
  if (r !== 'confirm') return
  try {
    if (await deleteWithForce(force => api.deleteModel(m.id, force))) {
      toast.success(t('aiProviders.toast.modelDeleted'))
      emit('changed')
    }
  } catch (e) {
    toast.error(t('common.deleteFailed'), { description: apiErrorMessage(e) })
  }
}

// ---- 启用 / 停用 ----
const toggling = ref<number | null>(null)
const toggleActive = async (p: AIProvider, value: boolean) => {
  if (!value && providerUsage(p).length) {
    const r = await ask({
      title: t('aiProviders.disable.title', { name: p.name }),
      description: t('aiProviders.disable.description', { scenes: providerUsage(p).join(t('aiProviders.listSeparator')) }),
      confirmLabel: t('aiProviders.disable.confirm'),
      destructive: true,
    })
    if (r !== 'confirm') return
  }
  toggling.value = p.id
  try {
    await api.updateProvider(p.id, { is_active: value })
    emit('changed')
  } catch (e) {
    toast.error(t('common.operationFailed'), { description: apiErrorMessage(e) })
  } finally {
    toggling.value = null
  }
}

// ---- 编辑服务商 ----
const editOpen = ref(false)
const editing = ref<AIProvider | null>(null)
const editForm = ref({ name: '', interface_type: 'openai' as InterfaceType, base_url: '', api_key: '' })
const editTesting = ref(false)
const editTest = ref<{ ok: boolean, message: string } | null>(null)
const editSaving = ref(false)

const openEdit = (p: AIProvider) => {
  editing.value = p
  editForm.value = { name: p.name, interface_type: p.interface_type, base_url: p.base_url ?? '', api_key: '' }
  editTest.value = null
  editOpen.value = true
}

const testEdit = async () => {
  if (!editing.value) return
  editTesting.value = true
  editTest.value = null
  try {
    const res = await api.discover({
      provider_id: editing.value.id,
      interface_type: editForm.value.interface_type,
      base_url: editForm.value.base_url || null,
      api_key: editForm.value.api_key || undefined,
    })
    editTest.value = { ok: res.ok, message: res.message }
  } catch (e) {
    editTest.value = { ok: false, message: apiErrorMessage(e) }
  } finally {
    editTesting.value = false
  }
}

const saveEdit = async () => {
  if (!editing.value) return
  editSaving.value = true
  try {
    await api.updateProvider(editing.value.id, {
      name: editForm.value.name.trim(),
      interface_type: editForm.value.interface_type,
      base_url: editForm.value.base_url,
      ...(editForm.value.api_key ? { api_key: editForm.value.api_key } : {}),
    })
    toast.success(t('common.saved'))
    editOpen.value = false
    emit('changed')
  } catch (e) {
    toast.error(t('common.saveFailed'), { description: apiErrorMessage(e) })
  } finally {
    editSaving.value = false
  }
}

// ---- 添加模型（自动拉取列表） ----
const addOpen = ref(false)
const addTarget = ref<AIProvider | null>(null)
const addLoading = ref(false)
const addMessage = ref('')
const addCandidates = ref<AIModelInput[]>([])
const addSelected = ref<AIModelInput[]>([])
const addSaving = ref(false)

const openAddModels = async (p: AIProvider) => {
  addTarget.value = p
  addCandidates.value = []
  addSelected.value = []
  addMessage.value = ''
  addOpen.value = true
  addLoading.value = true
  try {
    const res = await api.discover({ provider_id: p.id })
    addCandidates.value = res.models
    addMessage.value = res.ok ? '' : t('aiProviders.discoverFailed', { message: res.message })
  } catch (e) {
    addMessage.value = t('aiProviders.discoverFailed', { message: apiErrorMessage(e) })
  } finally {
    addLoading.value = false
  }
}

const saveAddModels = async () => {
  if (!addTarget.value || !addSelected.value.length) return
  addSaving.value = true
  try {
    for (const m of addSelected.value) await api.addModel(addTarget.value.id, m)
    toast.success(t('aiProviders.toast.modelsAdded', { count: addSelected.value.length }))
    addOpen.value = false
    emit('changed')
  } catch (e) {
    toast.error(t('aiProviders.wizard.addFailed'), { description: apiErrorMessage(e) })
    emit('changed')
  } finally {
    addSaving.value = false
  }
}

// ---- 编辑模型 ----
const modelOpen = ref(false)
const modelEditing = ref<AIModel | null>(null)
const modelForm = ref<AIModelInput>({ name: '', is_vision_capable: false, is_embedding_model: false })

const openModelEdit = (m: AIModel) => {
  modelEditing.value = m
  modelForm.value = { name: m.name, is_vision_capable: m.is_vision_capable, is_embedding_model: m.is_embedding_model }
  modelOpen.value = true
}

const saveModel = async () => {
  if (!modelEditing.value) return
  try {
    await api.updateModel(modelEditing.value.id, modelForm.value)
    toast.success(t('aiProviders.toast.modelUpdated'))
    modelOpen.value = false
    emit('changed')
  } catch (e) {
    toast.error(t('common.saveFailed'), { description: apiErrorMessage(e) })
  }
}
</script>

<template>
  <div class="grid gap-4 md:grid-cols-2">
    <Card v-for="p in providers" :key="p.id" :class="['flex flex-col gap-0 py-0', !p.is_active && 'opacity-70']">
      <CardHeader class="flex flex-row items-start justify-between gap-2 space-y-0 border-b px-4 py-3">
        <div class="min-w-0">
          <CardTitle class="flex items-center gap-2 text-base">
            <span class="truncate">{{ p.name }}</span>
            <Badge v-if="!p.is_active" variant="secondary" class="font-normal">{{ t('aiProviders.disabled') }}</Badge>
          </CardTitle>
          <div class="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <span v-if="review && p.owner_name" class="flex items-center gap-1"><User class="h-3 w-3" />{{ p.owner_name }}</span>
            <span>{{ INTERFACE_LABEL_KEYS[p.interface_type] ? t(INTERFACE_LABEL_KEYS[p.interface_type]!) : p.interface_type }}</span>
            <span v-if="p.base_url" class="flex min-w-0 items-center gap-1" :title="p.base_url">
              <Link2 class="h-3 w-3 shrink-0" /><span class="truncate max-w-48">{{ p.base_url }}</span>
            </span>
            <span v-if="!p.api_key_set" class="flex items-center gap-1 text-destructive"><KeyRound class="h-3 w-3" />{{ t('aiProviders.keyNotSet') }}</span>
          </div>
        </div>

        <div class="flex shrink-0 items-center gap-1">
          <template v-if="!review">
            <Switch
              :model-value="p.is_active"
              :disabled="toggling === p.id"
              :aria-label="p.is_active ? t('aiProviders.disable.confirm') : t('aiProviders.enable')"
              @update:model-value="v => toggleActive(p, !!v)"
            />
            <DropdownMenu>
              <DropdownMenuTrigger as-child>
                <Button variant="ghost" size="icon" class="h-8 w-8" :aria-label="t('common.moreActions')">
                  <MoreHorizontal class="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem @click="openEdit(p)"><Pencil class="mr-2 h-4 w-4" />{{ t('aiProviders.editConnection') }}</DropdownMenuItem>
                <DropdownMenuItem @click="openAddModels(p)"><Plus class="mr-2 h-4 w-4" />{{ t('aiProviders.addModels') }}</DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem class="text-destructive focus:text-destructive" @click="removeProvider(p)">
                  <Trash2 class="mr-2 h-4 w-4" />{{ t('aiProviders.deleteProvider.action') }}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </template>
          <Button v-else variant="ghost" size="sm" class="text-destructive" @click="removeProvider(p)">
            <Trash2 class="mr-1 h-4 w-4" />{{ t('common.delete') }}
          </Button>
        </div>
      </CardHeader>

      <CardContent class="flex-1 px-2 py-2">
        <ul class="divide-y">
          <li v-for="m in p.models" :key="m.id" class="flex items-center gap-2 px-2 py-1.5 text-sm">
            <span class="min-w-0 flex-1 truncate font-mono text-xs" :title="m.name">{{ m.name }}</span>
            <Badge v-if="m.is_vision_capable" variant="outline" class="h-5 gap-1 border-blue-200 bg-blue-50 px-1.5 text-[11px] font-normal text-blue-700">
              <ImageIcon class="h-3 w-3" />{{ t('aiModels.capabilities.vision') }}
            </Badge>
            <Badge v-if="m.is_embedding_model" variant="outline" class="h-5 gap-1 border-purple-200 bg-purple-50 px-1.5 text-[11px] font-normal text-purple-700">
              <Search class="h-3 w-3" />{{ t('aiModels.capabilities.embedding') }}
            </Badge>
            <Badge v-for="u in usage.get(m.id) ?? []" :key="u" class="h-5 px-1.5 text-[11px] font-normal">
              {{ u }}
            </Badge>
            <template v-if="!review">
              <Button variant="ghost" size="icon" class="h-7 w-7" :aria-label="t('aiProviders.editModelAria', { name: m.name })" @click="openModelEdit(m)">
                <Pencil class="h-3.5 w-3.5 text-muted-foreground" />
              </Button>
              <Button variant="ghost" size="icon" class="h-7 w-7" :aria-label="t('aiProviders.deleteModelAria', { name: m.name })" @click="removeModel(m)">
                <Trash2 class="h-3.5 w-3.5 text-muted-foreground" />
              </Button>
            </template>
          </li>
        </ul>
        <div v-if="!p.models.length" class="px-2 py-3 text-center text-xs text-muted-foreground">
          {{ t('aiProviders.noModels') }}
          <button v-if="!review" type="button" class="underline" @click="openAddModels(p)">{{ t('aiProviders.addModels') }}</button>
        </div>
        <Button v-else-if="!review" variant="ghost" size="sm" class="mt-1 w-full text-muted-foreground" @click="openAddModels(p)">
          <Plus class="mr-1 h-4 w-4" />{{ t('aiProviders.addModels') }}
        </Button>
      </CardContent>
    </Card>
  </div>

  <!-- 编辑服务商 -->
  <Dialog v-model:open="editOpen">
    <DialogContent>
      <DialogHeader>
        <DialogTitle>{{ t('aiProviders.edit.title') }}</DialogTitle>
        <DialogDescription>{{ t('aiProviders.edit.description') }}</DialogDescription>
      </DialogHeader>
      <form class="grid gap-4" @submit.prevent="saveEdit">
        <div class="grid gap-2">
          <Label for="pe-name">{{ t('common.name') }}</Label>
          <Input id="pe-name" v-model="editForm.name" />
        </div>
        <div class="grid gap-2">
          <Label>{{ t('aiProviders.interfaceType') }}</Label>
          <Select v-model="editForm.interface_type">
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="openai">{{ t(INTERFACE_LABEL_KEYS.openai!) }}</SelectItem>
              <SelectItem value="gemini">{{ t(INTERFACE_LABEL_KEYS.gemini!) }}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div class="grid gap-2">
          <Label for="pe-url">{{ t('aiProviders.baseUrl') }}</Label>
          <Input id="pe-url" v-model="editForm.base_url" :placeholder="t('aiProviders.baseUrlPlaceholderGemini')" />
        </div>
        <div class="grid gap-2">
          <Label for="pe-key">API Key</Label>
          <Input
            id="pe-key"
            v-model="editForm.api_key"
            type="password"
            autocomplete="off"
            :placeholder="editing?.api_key_set ? t('aiProviders.edit.keySet') : t('aiProviders.edit.keyRequired')"
          />
        </div>
        <div class="flex items-center gap-3 text-sm">
          <Button type="button" variant="outline" size="sm" :disabled="editTesting" @click="testEdit">
            <Loader2 v-if="editTesting" class="mr-2 h-4 w-4 animate-spin" />{{ t('aiProviders.testConnection') }}
          </Button>
          <span v-if="editTest" :class="editTest.ok ? 'text-green-600' : 'text-destructive'">{{ editTest.message }}</span>
        </div>
        <DialogFooter>
          <Button type="submit" :disabled="editSaving || !editForm.name.trim()">{{ t('common.save') }}</Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>

  <!-- 添加模型 -->
  <Dialog v-model:open="addOpen">
    <DialogContent class="sm:max-w-xl">
      <DialogHeader>
        <DialogTitle>{{ t('aiProviders.addModelsDialog.title', { name: addTarget?.name ?? '' }) }}</DialogTitle>
        <DialogDescription>{{ t('aiProviders.addModelsDialog.description') }}</DialogDescription>
      </DialogHeader>
      <div v-if="addLoading" class="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
        <Loader2 class="h-4 w-4 animate-spin" />{{ t('aiProviders.addModelsDialog.loading') }}
      </div>
      <template v-else>
        <p v-if="addMessage" class="text-sm text-amber-600">{{ addMessage }}</p>
        <ModelPicker
          v-model="addSelected"
          :candidates="addCandidates"
          :existing-names="addTarget?.models.map(m => m.name)"
        />
      </template>
      <DialogFooter>
        <Button :disabled="addSaving || !addSelected.length" @click="saveAddModels">
          <Loader2 v-if="addSaving" class="mr-2 h-4 w-4 animate-spin" />{{ addSelected.length ? t('aiProviders.addModelsCount', { count: addSelected.length }) : t('aiProviders.addModels') }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>

  <!-- 编辑模型 -->
  <Dialog v-model:open="modelOpen">
    <DialogContent>
      <DialogHeader>
        <DialogTitle>{{ t('aiProviders.editModel.title') }}</DialogTitle>
        <DialogDescription>{{ t('aiProviders.editModel.description') }}</DialogDescription>
      </DialogHeader>
      <form class="grid gap-4" @submit.prevent="saveModel">
        <div class="grid gap-2">
          <Label for="me-name">{{ t('aiModels.modelName') }}</Label>
          <Input id="me-name" v-model="modelForm.name" class="font-mono" />
        </div>
        <div class="flex items-center gap-2">
          <Checkbox
            id="me-vision"
            :model-value="modelForm.is_vision_capable"
            :disabled="modelForm.is_embedding_model"
            @update:model-value="v => modelForm.is_vision_capable = !!v"
          />
          <Label for="me-vision">{{ t('aiModels.visionCapable') }}</Label>
        </div>
        <div class="flex items-center gap-2">
          <Checkbox
            id="me-embedding"
            :model-value="modelForm.is_embedding_model"
            @update:model-value="v => { modelForm.is_embedding_model = !!v; if (v) modelForm.is_vision_capable = false }"
          />
          <Label for="me-embedding">{{ t('aiModels.embeddingModel') }}</Label>
        </div>
        <DialogFooter>
          <Button type="submit" :disabled="!modelForm.name.trim()">{{ t('common.save') }}</Button>
        </DialogFooter>
      </form>
    </DialogContent>
  </Dialog>

  <ConfirmDialog ref="confirmRef" />
</template>
