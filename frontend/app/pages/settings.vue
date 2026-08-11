<script setup lang="ts">
import { ref, onMounted, watchEffect } from 'vue'
import { useRouter } from 'vue-router'
import { toast } from 'vue-sonner'
import { Settings, Cpu, MessageSquareText } from '@lucide/vue'
import PageHeader from '~/components/PageHeader.vue'
import AiSettings from '~/components/AiSettings.vue'
import AiPromptsConfig from '~/components/AiPromptsConfig.vue'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'

const { $api } = useNuxtApp()
const { user } = useAuth()
const router = useRouter()

// Navigation State
const activeTab = ref('general')
const updateActiveTab = (tab: string) => {
  activeTab.value = tab
}

// Redirect if not superuser
watchEffect(() => {
  if (user.value && !user.value.is_superuser) {
    router.push('/')
  }
})

interface SystemSetting {
  key: string
  value: string
  description: string
}

const settings = ref<SystemSetting[]>([])
const loading = ref(false)

const fetchSettings = async () => {
  loading.value = true
  try {
    const data = await $api<SystemSetting[]>('/settings')
    // Filter out settings managed by AI Config UI or AI Prompts config
    settings.value = data.filter(s => {
      const isConfigModelId = ['AI_TEXT_MODEL_ID', 'AI_VISION_MODEL_ID', 'AI_EMBEDDING_MODEL_ID'].includes(s.key)
      const isPrompt = s.key.endsWith('_PROMPT')
      return !isConfigModelId && !isPrompt
    })
  } catch (error) {
    toast.error('获取设置失败', {
      description: (error as any).message,
    })
  } finally {
    loading.value = false
  }
}

const updateSetting = async (setting: SystemSetting) => {
  try {
    await $api(`/settings/${setting.key}`, {
      method: 'PUT',
      body: {
        value: setting.value,
        description: setting.description,
      }
    })
    toast.success('保存成功', {
      description: `设置 ${setting.key} 已更新`,
    })
  } catch (error) {
    toast.error('保存失败', {
      description: (error as any).message,
    })
  }
}

onMounted(() => {
  if (user.value?.is_superuser) {
    fetchSettings()
  }
})
</script>

<template>
  <PageHeader title="系统设置" />
  
  <div class="flex flex-col md:flex-row max-w-7xl mx-auto w-full items-stretch min-h-[calc(100vh-4rem)]">
    <!-- Left Sidebar Navigation -->
    <aside class="w-full md:w-56 shrink-0 md:border-r border-border p-4 md:pr-6 md:pt-8 bg-muted/20 md:bg-transparent">
      <nav class="flex flex-row md:flex-col gap-1 overflow-x-auto md:overflow-visible pb-2 md:pb-0 md:sticky md:top-8">
        <Button 
          :variant="activeTab === 'general' ? 'secondary' : 'ghost'" 
          class="justify-start gap-2 whitespace-nowrap lg:w-full"
          @click="updateActiveTab('general')"
        >
          <Settings class="w-4 h-4" />
          常规设置
        </Button>
        <Button 
          :variant="activeTab === 'ai' ? 'secondary' : 'ghost'" 
          class="justify-start gap-2 whitespace-nowrap lg:w-full"
          @click="updateActiveTab('ai')"
        >
          <Cpu class="w-4 h-4" />
          AI 大脑核心
        </Button>
        <Button 
          :variant="activeTab === 'prompts' ? 'secondary' : 'ghost'" 
          class="justify-start gap-2 whitespace-nowrap lg:w-full"
          @click="updateActiveTab('prompts')"
        >
          <MessageSquareText class="w-4 h-4" />
          系统提示词
        </Button>
      </nav>
    </aside>

    <!-- Right Content Area -->
    <main class="flex-1 min-w-0 p-4 md:pl-8 md:pt-8 mt-4 md:mt-0">
      <!-- General Settings -->
      <div v-show="activeTab === 'general'" class="space-y-6">
        <div class="mb-4">
          <h2 class="text-2xl font-bold tracking-tight">常规设置</h2>
          <p class="text-sm text-muted-foreground">管理系统的全局环境变量与基础配置。</p>
        </div>

        <div v-if="loading" class="flex justify-center py-8">
          <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
        </div>

        <div v-else class="grid gap-6">
          <Card v-for="setting in settings" :key="setting.key">
            <CardHeader>
              <CardTitle class="text-base">{{ setting.key }}</CardTitle>
              <CardDescription>{{ setting.description }}</CardDescription>
            </CardHeader>
            <CardContent>
              <div class="flex flex-col gap-4">
                <div class="grid w-full items-center gap-1.5">
                  <Textarea
                    v-if="setting.key === 'AI_EXTRACT_PROMPT' || setting.value.length > 100"
                    v-model="setting.value"
                    placeholder="Value"
                    class="min-h-[200px] font-mono text-sm"
                  />
                  <Input 
                    v-else
                    v-model="setting.value" 
                    :type="setting.key.includes('KEY') || setting.key.includes('SECRET') ? 'password' : 'text'" 
                    placeholder="Value" 
                  />
                </div>
                <div class="flex justify-end">
                  <Button @click="updateSetting(setting)">保存设置</Button>
                </div>
              </div>
            </CardContent>
          </Card>
          
          <div v-if="settings.length === 0" class="flex flex-col items-center justify-center p-12 text-center border rounded-xl bg-card border-dashed">
            <Settings class="w-8 h-8 text-muted-foreground/50 mb-4" />
            <h3 class="text-lg font-medium">暂无设置项</h3>
            <p class="text-sm text-muted-foreground mt-1">系统尚未注册任何开放配置项</p>
          </div>
        </div>
      </div>

      <!-- AI Settings -->
      <div v-show="activeTab === 'ai'">
        <div class="mb-6">
          <h2 class="text-2xl font-bold tracking-tight">AI 大脑核心</h2>
          <p class="text-sm text-muted-foreground">分配提供商、录入模型，并配置系统各场景下的主力计算引擎。</p>
        </div>
        <AiSettings />
      </div>

      <!-- AI Prompts -->
      <div v-show="activeTab === 'prompts'">
        <div class="mb-6">
          <h2 class="text-2xl font-bold tracking-tight">系统提示词 (Prompts)</h2>
          <p class="text-sm text-muted-foreground">如果您了解大语言工作原理，可在此微调它处理指令的方式。</p>
        </div>
        <AiPromptsConfig />
      </div>
    </main>
  </div>
</template>
