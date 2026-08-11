<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { toast } from 'vue-sonner'
import { Save, MessageSquareText } from '@lucide/vue'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'

const { $api } = useNuxtApp()

interface SystemSetting {
  key: string
  value: string
  description: string
}

const promptSettings = ref<SystemSetting[]>([])
const loading = ref(false)

const fetchPrompts = async () => {
  loading.value = true
  try {
    const data = await $api<SystemSetting[]>('/settings')
    // Filter only AI settings that are prompts, ignore model IDs
    promptSettings.value = data.filter(s => s.key.endsWith('_PROMPT') && s.key.startsWith('AI_'))
  } catch (error) {
    toast.error('获取提示词失败', {
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
      description: `提示词 ${setting.key} 已更新`,
    })
  } catch (error) {
    toast.error('保存失败', {
      description: (error as any).message,
    })
  }
}

onMounted(() => {
  fetchPrompts()
})
</script>

<template>
  <div class="space-y-6">
    <div v-if="loading" class="flex justify-center py-8">
      <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
    </div>

    <div v-else class="grid gap-6 max-w-3xl">
      <Card v-for="setting in promptSettings" :key="setting.key">
        <CardHeader>
          <CardTitle class="text-base flex items-center gap-2">
            <MessageSquareText class="w-4 h-4 text-primary" />
            {{ setting.key }}
          </CardTitle>
          <CardDescription>{{ setting.description }}</CardDescription>
        </CardHeader>
        <CardContent>
          <div class="flex flex-col gap-4">
             <Textarea
              v-model="setting.value"
              placeholder="请输入系统提示词..."
              class="min-h-[250px] font-mono text-sm leading-relaxed"
            />
            <div class="flex justify-end">
              <Button @click="updateSetting(setting)">
                <Save class="w-4 h-4 mr-2" />
                保存微调
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <div v-if="promptSettings.length === 0" class="flex flex-col items-center justify-center p-12 text-center border rounded-xl bg-card border-dashed">
        <MessageSquareText class="w-8 h-8 text-muted-foreground/50 mb-4" />
        <h3 class="text-lg font-medium">暂无提示词模板</h3>
        <p class="text-sm text-muted-foreground mt-1">系统没有暴露需要配置的 AI 提示词</p>
      </div>
    </div>
  </div>
</template>
