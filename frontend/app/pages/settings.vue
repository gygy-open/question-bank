<script setup lang="ts">
import { toast } from 'vue-sonner'
import PageHeader from '~/components/PageHeader.vue'
import AiSettings from '~/components/AiSettings.vue'
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

const { $api } = useNuxtApp()
const { user } = useAuth()
const router = useRouter()

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
    // Filter out settings managed by AI Config UI
    settings.value = data.filter(s => !['AI_TEXT_MODEL_ID', 'AI_VISION_MODEL_ID'].includes(s.key))
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
  <div class="flex flex-1 flex-col p-4 space-y-6">
    <Tabs default-value="general" class="w-full">
      <TabsList class="grid w-full grid-cols-2 max-w-[400px]">
        <TabsTrigger value="general">常规设置</TabsTrigger>
        <TabsTrigger value="ai">AI 模型配置</TabsTrigger>
      </TabsList>

      <TabsContent value="general" class="space-y-6">
        <div v-if="loading" class="flex justify-center py-8">
          <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
        </div>

        <div v-else class="grid gap-6 max-w-3xl">
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
                    class="min-h-[200px]"
                  />
                  <Input 
                    v-else
                    v-model="setting.value" 
                    :type="setting.key.includes('KEY') || setting.key.includes('SECRET') ? 'password' : 'text'" 
                    placeholder="Value" 
                  />
                </div>
                <div class="flex justify-end">
                  <Button @click="updateSetting(setting)">保存</Button>
                </div>
              </div>
            </CardContent>
          </Card>
          
          <div v-if="settings.length === 0" class="text-center text-muted-foreground py-8">
            暂无设置项
          </div>
        </div>
      </TabsContent>

      <TabsContent value="ai">
        <AiSettings />
      </TabsContent>
    </Tabs>
  </div>
</template>
