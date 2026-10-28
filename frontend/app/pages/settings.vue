<script setup lang="ts">
import { ref, computed, onMounted, watchEffect } from 'vue'
import { toast } from 'vue-sonner'
import { Settings, Cpu, MessageSquareText, UserPlus, Sparkles, Plug } from '@lucide/vue'
import PageHeader from '~/components/PageHeader.vue'
import AiSettings from '~/components/AiSettings.vue'
import MyAiSettings from '~/components/MyAiSettings.vue'
import AiPromptsConfig from '~/components/AiPromptsConfig.vue'
import McpSettings from '~/components/mcp/McpSettings.vue'
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
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'

const { t } = useI18n()
const { $api } = useNuxtApp()
const { user } = useAuth()
const { permissions, isAdmin, isManagerSomewhere } = usePermissions()

// Navigation State
const activeTab = ref('general')
const updateActiveTab = (tab: string) => {
  activeTab.value = tab
}

const canEditPrompts = computed(() => isAdmin.value || isManagerSomewhere.value)

// 所有登录用户都能进入设置页管理自己的 AI 模型；系统级标签页仅管理员可见。
watchEffect(() => {
  if (!user.value || !permissions.value) return
  if (!isAdmin.value && ['general', 'ai', 'registration'].includes(activeTab.value)) {
    activeTab.value = 'my-ai'
  }
  if (!canEditPrompts.value && activeTab.value === 'prompts') {
    activeTab.value = 'my-ai'
  }
})

interface SystemSetting {
  key: string
  value: string
  description: string
}

const settings = ref<SystemSetting[]>([])
const loading = ref(false)

const REGISTRATION_ENABLED_KEY = 'USER_REGISTRATION_ENABLED'
const REGISTRATION_APPROVAL_KEY = 'USER_REGISTRATION_REQUIRES_APPROVAL'

const registrationEnabled = ref(false)
const registrationRequiresApproval = ref(false)
const registrationSaving = ref(false)

const fetchSettings = async () => {
  loading.value = true
  try {
    const data = await $api<SystemSetting[]>('/settings')
    // Filter out settings managed by AI Config UI or AI Prompts config
    settings.value = data.filter(s => {
      const isConfigModelId = ['AI_TEXT_MODEL_ID', 'AI_VISION_MODEL_ID', 'AI_EMBEDDING_MODEL_ID'].includes(s.key)
      const isPrompt = s.key.endsWith('_PROMPT')
      const isRegistration = [REGISTRATION_ENABLED_KEY, REGISTRATION_APPROVAL_KEY].includes(s.key)
      return !isConfigModelId && !isPrompt && !isRegistration
    })
    registrationEnabled.value = data.find(s => s.key === REGISTRATION_ENABLED_KEY)?.value === 'true'
    registrationRequiresApproval.value = data.find(s => s.key === REGISTRATION_APPROVAL_KEY)?.value === 'true'
  } catch (error) {
    toast.error(t('settings.toast.fetchFailed'), {
      description: (error as any).message,
    })
  } finally {
    loading.value = false
  }
}

const saveRegistrationSetting = async (key: string, value: boolean) => {
  registrationSaving.value = true
  try {
    await $api(`/settings/${key}`, {
      method: 'PUT',
      body: { value: value ? 'true' : 'false' },
    })
    toast.success(t('settings.toast.saveSuccess'))
  } catch (error) {
    toast.error(t('common.saveFailed'), { description: (error as any).message })
    await fetchSettings()
  } finally {
    registrationSaving.value = false
  }
}

const onToggleRegistration = (value: boolean) => {
  registrationEnabled.value = value
  saveRegistrationSetting(REGISTRATION_ENABLED_KEY, value)
}

const onToggleApproval = (value: boolean) => {
  registrationRequiresApproval.value = value
  saveRegistrationSetting(REGISTRATION_APPROVAL_KEY, value)
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
    toast.success(t('settings.toast.saveSuccess'), {
      description: t('settings.toast.settingUpdated', { key: setting.key }),
    })
  } catch (error) {
    toast.error(t('common.saveFailed'), {
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
  <PageHeader :title="isAdmin ? t('settings.titleAdmin') : t('settings.title')" />
  
  <div class="flex flex-col md:flex-row max-w-7xl mx-auto w-full items-stretch min-h-[calc(100vh-4rem)]">
    <!-- Left Sidebar Navigation -->
    <aside class="w-full md:w-56 shrink-0 md:border-r border-border p-4 md:pr-6 md:pt-8 bg-muted/20 md:bg-transparent">
      <nav class="flex flex-row md:flex-col gap-1 overflow-x-auto md:overflow-visible pb-2 md:pb-0 md:sticky md:top-8">
        <Button
          v-if="isAdmin"
          :variant="activeTab === 'general' ? 'secondary' : 'ghost'" 
          class="justify-start gap-2 whitespace-nowrap lg:w-full"
          @click="updateActiveTab('general')"
        >
          <Settings class="w-4 h-4" />
          {{ t('settings.nav.general') }}
        </Button>
        <Button
          v-if="isAdmin"
          :variant="activeTab === 'ai' ? 'secondary' : 'ghost'" 
          class="justify-start gap-2 whitespace-nowrap lg:w-full"
          @click="updateActiveTab('ai')"
        >
          <Cpu class="w-4 h-4" />
          {{ t('settings.nav.globalAi') }}
        </Button>
        <Button
          :variant="activeTab === 'my-ai' ? 'secondary' : 'ghost'" 
          class="justify-start gap-2 whitespace-nowrap lg:w-full"
          @click="updateActiveTab('my-ai')"
        >
          <Sparkles class="w-4 h-4" />
          {{ t('settings.nav.myAi') }}
        </Button>
        <Button
          v-if="canEditPrompts"
          :variant="activeTab === 'prompts' ? 'secondary' : 'ghost'" 
          class="justify-start gap-2 whitespace-nowrap lg:w-full"
          @click="updateActiveTab('prompts')"
        >
          <MessageSquareText class="w-4 h-4" />
          {{ t('settings.nav.prompts') }}
        </Button>
        <Button
          :variant="activeTab === 'mcp' ? 'secondary' : 'ghost'"
          class="justify-start gap-2 whitespace-nowrap lg:w-full"
          @click="updateActiveTab('mcp')"
        >
          <Plug class="w-4 h-4" />
          {{ t('settings.nav.mcp') }}
        </Button>
        <Button
          v-if="isAdmin"
          :variant="activeTab === 'registration' ? 'secondary' : 'ghost'" 
          class="justify-start gap-2 whitespace-nowrap lg:w-full"
          @click="updateActiveTab('registration')"
        >
          <UserPlus class="w-4 h-4" />
          {{ t('settings.nav.registration') }}
        </Button>
      </nav>
    </aside>

    <!-- Right Content Area -->
    <main class="flex-1 min-w-0 p-4 md:pl-8 md:pt-8 mt-4 md:mt-0">
      <!-- General Settings -->
      <div v-show="activeTab === 'general'" class="space-y-6">
        <div class="mb-4">
          <h2 class="text-2xl font-bold tracking-tight">{{ t('settings.nav.general') }}</h2>
          <p class="text-sm text-muted-foreground">{{ t('settings.general.description') }}</p>
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
                    :placeholder="t('settings.general.valuePlaceholder')"
                    class="min-h-[200px] font-mono text-sm"
                  />
                  <Input 
                    v-else
                    v-model="setting.value" 
                    :type="setting.key.includes('KEY') || setting.key.includes('SECRET') ? 'password' : 'text'" 
                    :placeholder="t('settings.general.valuePlaceholder')"
                  />
                </div>
                <div class="flex justify-end">
                  <Button @click="updateSetting(setting)">{{ t('settings.general.save') }}</Button>
                </div>
              </div>
            </CardContent>
          </Card>
          
          <div v-if="settings.length === 0" class="flex flex-col items-center justify-center p-12 text-center border rounded-xl bg-card border-dashed">
            <Settings class="w-8 h-8 text-muted-foreground/50 mb-4" />
            <h3 class="text-lg font-medium">{{ t('settings.general.emptyTitle') }}</h3>
            <p class="text-sm text-muted-foreground mt-1">{{ t('settings.general.emptyDescription') }}</p>
          </div>
        </div>
      </div>

      <!-- AI Settings -->
      <div v-if="isAdmin && activeTab === 'ai'">
        <div class="mb-6">
          <h2 class="text-2xl font-bold tracking-tight">{{ t('settings.nav.globalAi') }}</h2>
          <p class="text-sm text-muted-foreground">{{ t('settings.globalAi.description') }}</p>
        </div>
        <AiSettings />
      </div>

      <!-- My AI Settings -->
      <div v-if="activeTab === 'my-ai'">
        <div class="mb-6">
          <h2 class="text-2xl font-bold tracking-tight">{{ t('settings.nav.myAi') }}</h2>
          <p class="text-sm text-muted-foreground">{{ t('settings.myAi.description') }}</p>
        </div>
        <MyAiSettings />
      </div>

      <!-- AI Prompts -->
      <div v-if="canEditPrompts" v-show="activeTab === 'prompts'">
        <div class="mb-6">
          <h2 class="text-2xl font-bold tracking-tight">{{ t('settings.nav.prompts') }}</h2>
          <p class="text-sm text-muted-foreground">{{ t('settings.prompts.description') }}</p>
        </div>
        <AiPromptsConfig />
      </div>

      <!-- MCP -->
      <div v-if="activeTab === 'mcp'">
        <div class="mb-6">
          <h2 class="text-2xl font-bold tracking-tight">{{ t('settings.nav.mcp') }}</h2>
          <p class="text-sm text-muted-foreground">{{ t('settings.mcp.description') }}</p>
        </div>
        <McpSettings />
      </div>

      <!-- Registration Settings -->
      <div v-show="activeTab === 'registration'" class="space-y-6">
        <div class="mb-4">
          <h2 class="text-2xl font-bold tracking-tight">{{ t('settings.nav.registration') }}</h2>
          <p class="text-sm text-muted-foreground">{{ t('settings.registration.description') }}</p>
        </div>

        <Card>
          <CardContent class="pt-6 space-y-6">
            <div class="flex items-center justify-between gap-4">
              <div class="space-y-0.5">
                <Label class="text-base">{{ t('settings.registration.enabledLabel') }}</Label>
                <p class="text-sm text-muted-foreground">{{ t('settings.registration.enabledHint') }}</p>
              </div>
              <Switch
                :model-value="registrationEnabled"
                :disabled="registrationSaving"
                @update:model-value="onToggleRegistration"
              />
            </div>

            <div class="flex items-center justify-between gap-4">
              <div class="space-y-0.5">
                <Label class="text-base">{{ t('settings.registration.approvalLabel') }}</Label>
                <p class="text-sm text-muted-foreground">{{ t('settings.registration.approvalHint') }}</p>
              </div>
              <Switch
                :model-value="registrationRequiresApproval"
                :disabled="registrationSaving || !registrationEnabled"
                @update:model-value="onToggleApproval"
              />
            </div>
          </CardContent>
        </Card>
      </div>
    </main>
  </div>
</template>
