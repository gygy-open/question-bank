<script setup lang="ts">
import { toast } from 'vue-sonner'
import { Plus, Trash2, Save, RefreshCw, Pencil, Info, KeyRound, Cpu, Search, Image as ImageIcon, CheckCircle2, CircleDashed } from '@lucide/vue'
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
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'

const { $api } = useNuxtApp()

const PRESETS = [
  { name: 'DeepSeek', interface_type: 'openai', base_url: 'https://api.deepseek.com/v1' },
  { name: '智谱 AI (GLM)', interface_type: 'openai', base_url: 'https://open.bigmodel.cn/api/paas/v4' },
  { name: '千问 (Qwen)', interface_type: 'openai', base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
  { name: 'Kimi', interface_type: 'openai', base_url: 'https://api.moonshot.cn/v1' },
  { name: 'OpenAI', interface_type: 'openai', base_url: 'https://api.openai.com/v1' }
]

const applyPreset = (preset: typeof PRESETS[0]) => {
  newProvider.value.name = preset.name
  newProvider.value.interface_type = preset.interface_type as any
  newProvider.value.base_url = preset.base_url
}

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

const aiStatus = computed(() => {
  if (providers.value.length === 0) return 'no-providers'
  if (!activeConfig.value.text_model_id) return 'no-default'
  return 'ok'
})

// Auto-fill defaults if not set when adding a new provider
watch(() => providers.value, (newProviders) => {
  if (newProviders.length > 0) {
    let changed = false
    if (!activeConfig.value.text_model_id && allModels.value.length > 0) {
      activeConfig.value.text_model_id = allModels.value[0].id
      changed = true
    }
    if (!activeConfig.value.vision_model_id && visionModels.value.length > 0) {
      activeConfig.value.vision_model_id = visionModels.value[0].id
      changed = true
    }
    if (!activeConfig.value.embedding_model_id && embeddingModels.value.length > 0) {
      activeConfig.value.embedding_model_id = embeddingModels.value[0].id
      changed = true
    }
    if (changed) {
      saveActiveConfig()
    }
  }
}, { deep: true })

onMounted(() => {
  fetchData()
})
</script>

<template>
  <div class="space-y-8">
    <!-- Top Status Board -->
    <Alert v-if="aiStatus === 'no-providers'" class="border-destructive/50 bg-destructive/5 text-destructive">
      <CircleDashed class="w-4 h-4 text-destructive" />
      <AlertTitle>尚未连接 AI 服务大脑</AlertTitle>
      <AlertDescription>
        系统目前无法处理文档或图片识别。请在下方点击“添加 AI 服务商”开始接入。
      </AlertDescription>
    </Alert>

    <Alert v-else-if="aiStatus === 'no-default'" class="border-warning/50 bg-warning/5 text-amber-600">
      <Info class="w-4 h-4 text-amber-600" />
      <AlertTitle>缺少主要的模型分配</AlertTitle>
      <AlertDescription>
        您已经接入了服务商，但尚未分配主要处理模型。您可以在下方“高级：模型分配”中进行微调。
      </AlertDescription>
    </Alert>

    <Alert v-else class="border-green-500/50 bg-green-500/5 text-green-600">
      <CheckCircle2 class="w-4 h-4 text-green-600" />
      <AlertTitle>AI 大脑运行正常</AlertTitle>
      <AlertDescription>
        所有配置已就绪，系统核心智力和分析功能已激活。
      </AlertDescription>
    </Alert>

    <!-- Providers Matrix -->
    <div>
      <div class="flex items-center justify-between mb-4">
        <div>
          <h2 class="text-xl font-semibold tracking-tight">AI 账号池</h2>
          <p class="text-sm text-muted-foreground">在此处接入和管理为您提供算力的服务商。</p>
        </div>
        <Dialog v-model:open="isAddProviderOpen">
          <DialogTrigger as-child>
            <Button>
              <Plus class="w-4 h-4 mr-2" />
              添加 AI 服务商
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>添加 AI 服务商</DialogTitle>
              <DialogDescription>配置新的 AI 服务提供商信息</DialogDescription>
            </DialogHeader>
            <div class="grid gap-4 py-4">
              <div class="space-y-2 mb-2">
                <Label class="text-xs text-muted-foreground">🌟 快速填充常用配置</Label>
                <div class="flex flex-wrap gap-2">
                  <Button 
                    v-for="preset in PRESETS" 
                    :key="preset.name"
                    variant="outline" 
                    size="sm"
                    class="h-7 text-xs font-normal"
                    @click="applyPreset(preset)"
                  >
                    {{ preset.name }}
                  </Button>
                </div>
              </div>
              <div class="grid gap-2">
                <Label>显示名称</Label>
                <Input v-model="newProvider.name" placeholder="例如: 智谱大模型, OpenAI" />
              </div>
              <div class="grid gap-2">
                <Label>服务类型</Label>
                <Select v-model="newProvider.interface_type">
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="openai">OpenAI 兼容协议 (最常用)</SelectItem>
                    <SelectItem value="gemini">Google Gemini 协议</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div class="grid gap-2">
                <Label>API 接口地址 (Base URL)</Label>
                <Input v-model="newProvider.base_url" placeholder="例如: https://api.deepseek.com/v1" />
              </div>
              <div class="grid gap-2">
                <Label>密钥 (API Key)</Label>
                <div class="relative">
                  <KeyRound class="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                  <Input type="password" v-model="newProvider.api_key" placeholder="sk-..." class="pl-9" />
                </div>
              </div>
            </div>
            <DialogFooter>
              <Button @click="createProvider">完成添加</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      <div class="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        <Card v-for="provider in providers" :key="provider.id" class="flex flex-col hover:border-primary/50 transition-colors">
          <CardHeader>
            <div class="flex items-start justify-between">
              <div>
                <CardTitle class="text-lg">{{ provider.name }}</CardTitle>
                <CardDescription class="mt-1 flex items-center gap-2">
                  <Badge variant="secondary" class="font-normal">{{ provider.interface_type === 'openai' ? 'OpenAI 通用协议' : 'Gemini 协议' }}</Badge>
                  <span v-if="provider.is_active" class="flex h-2 w-2 rounded-full bg-green-500"></span>
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
              <div class="text-xs text-muted-foreground truncate hover:text-clip" v-if="provider.base_url">
                🔗 {{ provider.base_url }}
              </div>
              
              <div class="rounded-lg border bg-card p-3 shadow-sm">
                <div class="flex items-center justify-between mb-3">
                  <Label class="text-xs font-semibold text-muted-foreground">已录入的模型列表</Label>
                  <Button variant="ghost" size="sm" class="h-6 px-2 text-xs" @click="openAddModel(provider.id)">
                    <Plus class="w-3 h-3 mr-1" />
                    录入模型
                  </Button>
                </div>
                
                <div class="space-y-1.5">
                  <div 
                    v-for="model in provider.models" 
                    :key="model.id"
                    class="group flex items-center justify-between py-1.5 px-2 text-sm rounded bg-muted/30 hover:bg-muted/60 transition-colors"
                  >
                    <div class="flex items-center gap-2">
                      <span class="font-medium font-mono text-xs">{{ model.name }}</span>
                      <div class="flex gap-1">
                        <Badge v-if="model.is_vision_capable" variant="outline" class="text-[9px] h-4 px-1 rounded-sm border-blue-200 text-blue-600 bg-blue-50">识图</Badge>
                        <Badge v-if="model.is_embedding_model" variant="outline" class="text-[9px] h-4 px-1 rounded-sm border-purple-200 text-purple-600 bg-purple-50">搜索</Badge>
                      </div>
                    </div>
                    <Button variant="ghost" size="icon" class="w-5 h-5 opacity-0 group-hover:opacity-100 transition-opacity" @click="deleteModel(model.id)">
                      <Trash2 class="w-3 h-3 text-muted-foreground hover:text-destructive" />
                    </Button>
                  </div>
                  <div v-if="provider.models.length === 0" class="text-xs text-center text-muted-foreground italic py-2">
                    暂未录入模型，请点击上方添加
                  </div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
        
        <!-- Add Provider CTA Card -->
        <button 
          @click="isAddProviderOpen = true"
          class="flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-muted-foreground/25 p-6 hover:border-primary hover:bg-muted/20 transition-all text-muted-foreground hover:text-foreground h-full min-h-[220px]"
        >
          <div class="rounded-full bg-muted p-3">
            <Plus class="w-6 h-6" />
          </div>
          <div class="text-sm font-medium">接入新的服务商</div>
        </button>
      </div>
    </div>

    <!-- Advanced Configuration Accordion -->
    <Accordion type="single" collapsible class="w-full bg-card rounded-xl border px-4">
      <AccordionItem value="advanced-allocation" class="border-b-0">
        <AccordionTrigger class="hover:no-underline py-4">
          <div class="flex items-center gap-3">
            <div class="p-2 bg-primary/10 rounded-lg text-primary">
              <Cpu class="w-5 h-5" />
            </div>
            <div class="text-left">
              <h3 class="font-medium">高级：各场景模型分配</h3>
              <p class="text-xs text-muted-foreground mt-0.5 font-normal line-clamp-1">微调用于文档解析、图片识别和知识库搜索的具体模型 (默认已智能分配)</p>
            </div>
          </div>
        </AccordionTrigger>
        <AccordionContent class="pt-2 pb-6">
          <Separator class="mb-6" />
          <div class="grid gap-8 md:grid-cols-2">
            <!-- Text Model -->
            <div class="space-y-3">
              <div class="flex gap-3">
                <div class="mt-1 hidden sm:block">
                  <div class="p-2 bg-secondary rounded text-secondary-foreground"><Info class="w-4 h-4"/></div>
                </div>
                <div class="flex-1 space-y-1">
                  <Label class="text-sm font-semibold">基础问答与文档分析 🧠</Label>
                  <p class="text-[13px] text-muted-foreground">处理文本阅读、题目提取和日常对话的最佳大模型。</p>
                  <Select v-model="activeConfig.text_model_id" :disabled="loading">
                    <SelectTrigger class="mt-2">
                      <SelectValue placeholder="请选择主模型" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem v-for="model in allModels" :key="model.id" :value="model.id">
                        {{ model.providerName }} / {{ model.name }}
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>

            <!-- Vision Model -->
            <div class="space-y-3">
               <div class="flex gap-3">
                <div class="mt-1 hidden sm:block">
                  <div class="p-2 bg-secondary rounded text-secondary-foreground"><ImageIcon class="w-4 h-4"/></div>
                </div>
                <div class="flex-1 space-y-1">
                  <Label class="text-sm font-semibold">图片识别与解析 👁️</Label>
                  <p class="text-[13px] text-muted-foreground">负责看懂包含图表、公式的截图。需选择支持视觉能力(Vision)的模型。</p>
                  <Select v-model="activeConfig.vision_model_id" :disabled="loading">
                    <SelectTrigger class="mt-2">
                      <SelectValue placeholder="请选择识图模型" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem v-for="model in visionModels" :key="model.id" :value="model.id">
                        {{ model.providerName }} / {{ model.name }}
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>

            <!-- Embedding Model -->
            <div class="space-y-3">
              <div class="flex gap-3">
                <div class="mt-1 hidden sm:block">
                  <div class="p-2 bg-secondary rounded text-secondary-foreground"><Search class="w-4 h-4"/></div>
                </div>
                <div class="flex-1 space-y-1">
                  <Label class="text-sm font-semibold">本地知识库搜索引擎 🔎</Label>
                  <p class="text-[13px] text-muted-foreground">不解答问题，只负责将文字转换为数据，寻找相似题目。只需便宜快速的小模型。</p>
                  <Select v-model="activeConfig.embedding_model_id" :disabled="loading">
                    <SelectTrigger class="mt-2">
                      <SelectValue placeholder="请选择搜索/嵌入模型" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem v-for="model in embeddingModels" :key="model.id" :value="model.id">
                        {{ model.providerName }} / {{ model.name }}
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>
            
            <div class="md:col-span-2 pt-2 flex justify-end">
              <Button @click="saveActiveConfig" :disabled="savingConfig">
                <Save class="w-4 h-4 mr-2" />
                保存分配策略
              </Button>
            </div>
          </div>
        </AccordionContent>
      </AccordionItem>
    </Accordion>

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
