<script setup lang="ts">
import { toast } from 'vue-sonner'
import { Plus, Trash2, Save, RefreshCw, Pencil } from 'lucide-vue-next'
import type { AIProvider, AIModel, ActiveAIConfig, AIProviderCreate, AIProviderUpdate } from '~/types/ai-config'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  CardFooter,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Separator } from '@/components/ui/separator'
import { Badge } from '@/components/ui/badge'

const { $api } = useNuxtApp()

// State
const providers = ref<AIProvider[]>([])
const activeConfig = ref<ActiveAIConfig>({ text_model_id: null, vision_model_id: null, embedding_model_id: null })
const loading = ref(false)
const savingConfig = ref(false)

// New Provider Form
const isAddProviderOpen = ref(false)
const newProvider = ref<AIProviderCreate>({
  name: '',
  interface_type: 'openai',
  base_url: '',
  api_key: '',
  is_active: true,
  models: []
})

// Edit Provider Form
const isEditProviderOpen = ref(false)
const editingProviderId = ref<number | null>(null)
const editingProvider = ref<AIProviderUpdate>({
  name: '',
  interface_type: 'openai',
  base_url: '',
  api_key: '',
  is_active: true
})

// New Model Form
const isAddModelOpen = ref(false)
const selectedProviderId = ref<number | null>(null)
const newModel = ref({
  name: '',
  is_vision_capable: false,
  is_embedding_model: false
})

// Fetch Data
const fetchData = async () => {
  loading.value = true
  try {
    const [providersData, configData] = await Promise.all([
      $api<AIProvider[]>('/ai-config/providers'),
      $api<ActiveAIConfig>('/ai-config/active-config')
    ])
    providers.value = providersData
    activeConfig.value = configData
  } catch (error: any) {
    toast.error('加载配置失败', { description: error.message })
  } finally {
    loading.value = false
  }
}

// Active Config Actions
const saveActiveConfig = async () => {
  savingConfig.value = true
  try {
    await $api('/ai-config/active-config', {
      method: 'POST',
      body: activeConfig.value
    })
    toast.success('全局配置已保存')
  } catch (error: any) {
    toast.error('保存失败', { description: error.message })
  } finally {
    savingConfig.value = false
  }
}

// Provider Actions
const createProvider = async () => {
  try {
    await $api('/ai-config/providers', {
      method: 'POST',
      body: newProvider.value
    })
    toast.success('供应商已添加')
    isAddProviderOpen.value = false
    newProvider.value = {
      name: '',
      interface_type: 'openai',
      base_url: '',
      api_key: '',
      is_active: true,
      models: []
    }
    fetchData()
  } catch (error: any) {
    toast.error('添加失败', { description: error.message })
  }
}

const openEditProvider = (provider: AIProvider) => {
  editingProviderId.value = provider.id
  editingProvider.value = {
    name: provider.name,
    interface_type: provider.interface_type,
    base_url: provider.base_url || '',
    api_key: provider.api_key, // Note: API key might be masked in real app, but here we assume we can edit it or overwrite it
    is_active: provider.is_active
  }
  isEditProviderOpen.value = true
}

const updateProvider = async () => {
  if (!editingProviderId.value) return
  try {
    await $api(`/ai-config/providers/${editingProviderId.value}`, {
      method: 'PUT',
      body: editingProvider.value
    })
    toast.success('供应商已更新')
    isEditProviderOpen.value = false
    fetchData()
  } catch (error: any) {
    toast.error('更新失败', { description: error.message })
  }
}

const deleteProvider = async (id: number) => {
  if (!confirm('确定要删除这个供应商吗？这将同时删除其下的所有模型。')) return
  try {
    await $api(`/ai-config/providers/${id}`, { method: 'DELETE' })
    toast.success('供应商已删除')
    fetchData()
  } catch (error: any) {
    toast.error('删除失败', { description: error.message })
  }
}

// Model Actions
const openAddModel = (providerId: number) => {
  selectedProviderId.value = providerId
  newModel.value = { name: '', is_vision_capable: false, is_embedding_model: false }
  isAddModelOpen.value = true
}

const createModel = async () => {
  if (!selectedProviderId.value) return
  try {
    await $api(`/ai-config/providers/${selectedProviderId.value}/models`, {
      method: 'POST',
      body: newModel.value
    })
    toast.success('模型已添加')
    isAddModelOpen.value = false
    fetchData()
  } catch (error: any) {
    toast.error('添加失败', { description: error.message })
  }
}

const deleteModel = async (id: number) => {
  if (!confirm('确定要删除这个模型吗？')) return
  try {
    await $api(`/ai-config/models/${id}`, { method: 'DELETE' })
    toast.success('模型已删除')
    fetchData()
  } catch (error: any) {
    toast.error('删除失败', { description: error.message })
  }
}

// Computed
const allModels = computed(() => {
  return providers.value.flatMap(p => p.models.map(m => ({ ...m, providerName: p.name })))
})

const visionModels = computed(() => {
  return allModels.value.filter(m => m.is_vision_capable)
})

const embeddingModels = computed(() => {
  return allModels.value.filter(m => m.is_embedding_model)
})

onMounted(() => {
  fetchData()
})
</script>

<template>
  <div class="space-y-6">
    <!-- Global Configuration -->
    <Card>
      <CardHeader>
        <CardTitle>全局策略配置</CardTitle>
        <CardDescription>选择系统默认使用的 AI 模型</CardDescription>
      </CardHeader>
      <CardContent class="grid gap-6 md:grid-cols-2">
        <div class="space-y-2">
          <Label>默认文本提取模型</Label>
          <Select v-model="activeConfig.text_model_id" :disabled="loading">
            <SelectTrigger>
              <SelectValue placeholder="选择模型" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem 
                v-for="model in allModels" 
                :key="model.id" 
                :value="model.id"
              >
                {{ model.providerName }} - {{ model.name }}
              </SelectItem>
            </SelectContent>
          </Select>
          <p class="text-sm text-muted-foreground">用于从文档和文本中提取题目</p>
        </div>

        <div class="space-y-2">
          <Label>默认图像识别模型</Label>
          <Select v-model="activeConfig.vision_model_id" :disabled="loading">
            <SelectTrigger>
              <SelectValue placeholder="选择模型" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem 
                v-for="model in visionModels" 
                :key="model.id" 
                :value="model.id"
              >
                {{ model.providerName }} - {{ model.name }}
              </SelectItem>
            </SelectContent>
          </Select>
          <p class="text-sm text-muted-foreground">用于识别图片中的题目（需支持 Vision 能力）</p>
        </div>

        <div class="space-y-2">
          <Label>默认嵌入模型 (Embedding)</Label>
          <Select v-model="activeConfig.embedding_model_id" :disabled="loading">
            <SelectTrigger>
              <SelectValue placeholder="选择模型" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem 
                v-for="model in embeddingModels" 
                :key="model.id" 
                :value="model.id"
              >
                {{ model.providerName }} - {{ model.name }}
              </SelectItem>
            </SelectContent>
          </Select>
          <p class="text-sm text-muted-foreground">用于知识点向量化和相似度搜索</p>
        </div>
      </CardContent>
      <CardFooter>
        <Button @click="saveActiveConfig" :disabled="savingConfig">
          <Save class="w-4 h-4 mr-2" />
          保存全局配置
        </Button>
      </CardFooter>
    </Card>

    <div class="flex items-center justify-between">
      <h2 class="text-lg font-semibold">供应商管理</h2>
      <Dialog v-model:open="isAddProviderOpen">
        <DialogTrigger as-child>
          <Button>
            <Plus class="w-4 h-4 mr-2" />
            添加供应商
          </Button>
        </DialogTrigger>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>添加 AI 供应商</DialogTitle>
            <DialogDescription>配置新的 AI 服务提供商信息</DialogDescription>
          </DialogHeader>
          <div class="grid gap-4 py-4">
            <div class="grid gap-2">
              <Label>名称</Label>
              <Input v-model="newProvider.name" placeholder="例如: DeepSeek, Official OpenAI" />
            </div>
            <div class="grid gap-2">
              <Label>接口类型</Label>
              <Select v-model="newProvider.interface_type">
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="openai">OpenAI Compatible</SelectItem>
                  <SelectItem value="gemini">Google Gemini</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div class="grid gap-2">
              <Label>Base URL (可选)</Label>
              <Input v-model="newProvider.base_url" placeholder="例如: https://api.deepseek.com/v1" />
            </div>
            <div class="grid gap-2">
              <Label>API Key</Label>
              <Input v-model="newProvider.api_key" placeholder="sk-..." />
            </div>
          </div>
          <DialogFooter>
            <Button @click="createProvider">添加</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>

    <!-- Providers List -->
    <div class="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
      <Card v-for="provider in providers" :key="provider.id" class="flex flex-col">
        <CardHeader>
          <div class="flex items-start justify-between">
            <div>
              <CardTitle class="text-base">{{ provider.name }}</CardTitle>
              <CardDescription class="mt-1">
                <Badge variant="outline">{{ provider.interface_type }}</Badge>
              </CardDescription>
            </div>
            <div class="flex gap-1">
              <Button variant="ghost" size="icon" @click="openEditProvider(provider)">
                <Pencil class="w-4 h-4 text-muted-foreground" />
              </Button>
              <Button variant="ghost" size="icon" @click="deleteProvider(provider.id)">
                <Trash2 class="w-4 h-4 text-destructive" />
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent class="flex-1">
          <div class="space-y-4">
            <div class="text-sm text-muted-foreground break-all" v-if="provider.base_url">
              {{ provider.base_url }}
            </div>
            
            <Separator />
            
            <div class="space-y-2">
              <div class="flex items-center justify-between">
                <Label class="text-xs font-semibold uppercase text-muted-foreground">已配置模型</Label>
                <Button variant="ghost" size="sm" class="h-6 px-2" @click="openAddModel(provider.id)">
                  <Plus class="w-3 h-3 mr-1" />
                  添加
                </Button>
              </div>
              
              <div class="space-y-2">
                <div 
                  v-for="model in provider.models" 
                  :key="model.id"
                  class="flex items-center justify-between p-2 text-sm border rounded-md bg-muted/50"
                >
                  <div class="flex items-center gap-2">
                    <span>{{ model.name }}</span>
                    <Badge v-if="model.is_vision_capable" variant="secondary" class="text-[10px] h-4 px-1">Vision</Badge>
                    <Badge v-if="model.is_embedding_model" variant="outline" class="text-[10px] h-4 px-1">Embedding</Badge>
                  </div>
                  <Button variant="ghost" size="icon" class="w-6 h-6" @click="deleteModel(model.id)">
                    <Trash2 class="w-3 h-3 text-muted-foreground hover:text-destructive" />
                  </Button>
                </div>
                <div v-if="provider.models.length === 0" class="text-sm text-muted-foreground italic">
                  暂无模型
                </div>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>

    <!-- Edit Provider Dialog -->
    <Dialog v-model:open="isEditProviderOpen">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>编辑供应商</DialogTitle>
          <DialogDescription>修改 AI 服务提供商信息</DialogDescription>
        </DialogHeader>
        <div class="grid gap-4 py-4">
          <div class="grid gap-2">
            <Label>名称</Label>
            <Input v-model="editingProvider.name" placeholder="例如: DeepSeek, Official OpenAI" />
          </div>
          <div class="grid gap-2">
            <Label>接口类型</Label>
            <Select v-model="editingProvider.interface_type">
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="openai">OpenAI Compatible</SelectItem>
                <SelectItem value="gemini">Google Gemini</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div class="grid gap-2">
            <Label>Base URL (可选)</Label>
            <Input v-model="editingProvider.base_url" placeholder="例如: https://api.deepseek.com/v1" />
          </div>
          <div class="grid gap-2">
            <Label>API Key</Label>
            <Input v-model="editingProvider.api_key" placeholder="留空则不修改" />
          </div>
        </div>
        <DialogFooter>
          <Button @click="updateProvider">保存修改</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Add Model Dialog -->
    <Dialog v-model:open="isAddModelOpen">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>添加模型</DialogTitle>
          <DialogDescription>为供应商添加支持的模型</DialogDescription>
        </DialogHeader>
        <div class="grid gap-4 py-4">
          <div class="grid gap-2">
            <Label>模型名称 (Model ID)</Label>
            <Input v-model="newModel.name" placeholder="例如: gpt-4o, gemini-1.5-pro" />
            <p class="text-xs text-muted-foreground">请填写 API 调用时使用的准确模型标识符</p>
          </div>
          <div class="flex items-center space-x-2">
            <Checkbox 
              id="vision" 
              :checked="newModel.is_vision_capable"
              @update:model-value="(v) => newModel.is_vision_capable = !!v"
            />
            <Label htmlFor="vision">支持视觉 (Vision Capable)</Label>
          </div>
          <div class="flex items-center space-x-2">
            <Checkbox 
              id="embedding" 
              :checked="newModel.is_embedding_model"
              @update:model-value="(v) => newModel.is_embedding_model = !!v"
            />
            <Label htmlFor="embedding">嵌入模型 (Embedding Model)</Label>
          </div>
        </div>
        <DialogFooter>
          <Button @click="createModel">添加</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
