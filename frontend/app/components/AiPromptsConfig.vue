<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { toast } from 'vue-sonner'
import { Save, MessageSquareText, FileText, BrainCircuit, MessageCircle, Wrench } from '@lucide/vue'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'

const { $api } = useNuxtApp()

interface SystemSetting {
  key: string
  value: string
  description: string
}

// Map technical prompt keys to user-friendly titles and icons
const promptMetaMap: Record<string, { title: string, icon: any, desc: string }> = {
  'AI_EXTRACT_PROMPT': {
    title: '文档题目提取助手',
    icon: FileText,
    desc: '控制 AI 从上传的 Word 或图片中识别并拆分题干与选项的行为准则。'
  },
  'AI_SOLVE_PROMPT': {
    title: '解题推理分析助手',
    icon: BrainCircuit,
    desc: '定义 AI 在生成题目解析和答案时，应该遵循的数学逻辑和排版格式。'
  },
  'CHAT_SYSTEM_PROMPT': {
    title: '全局聊天设定',
    icon: MessageCircle,
    desc: '系统 AI 助手的默认角色设定和基础性格，控制日常对话风格。'
  }
}

const promptSettings = ref<SystemSetting[]>([])
const loading = ref(false)

const fetchPrompts = async () => {
  loading.value = true
  try {
    const data = await $api<SystemSetting[]>('/settings')
    // Filter only AI settings that are prompts, ignore model IDs
    promptSettings.value = data.filter(s => s.key.endsWith('_PROMPT'))
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

    <div v-else class="max-w-4xl">
      <Accordion type="single" collapsible class="w-full space-y-4">
        <AccordionItem 
          v-for="setting in promptSettings" 
          :key="setting.key" 
          :value="setting.key"
          class="border rounded-xl bg-card px-4"
        >
          <AccordionTrigger class="hover:no-underline py-4">
            <div class="flex items-center gap-4 text-left">
              <div class="p-2.5 bg-primary/10 rounded-lg text-primary shrink-0">
                <component :is="promptMetaMap[setting.key]?.icon || Wrench" class="w-5 h-5" />
              </div>
              <div>
                <div class="flex items-center gap-2">
                  <h3 class="font-semibold text-base">{{ promptMetaMap[setting.key]?.title || '未知功能提示词' }}</h3>
                  <Badge variant="outline" class="text-[10px] font-mono py-0 h-4">{{ setting.key }}</Badge>
                </div>
                <p class="text-xs text-muted-foreground mt-0.5 line-clamp-1 font-normal">
                  {{ promptMetaMap[setting.key]?.desc || setting.description || '用于精细化调整大语言模型响应行为的指令集。' }}
                </p>
              </div>
            </div>
          </AccordionTrigger>
          <AccordionContent class="pt-2 pb-6">
            <div class="flex flex-col gap-4 pl-[3.25rem]">
              <Textarea
                v-model="setting.value"
                placeholder="请输入系统提示词..."
                class="min-h-[300px] font-mono text-[13px] leading-relaxed resize-y bg-muted/30 focus:bg-background"
              />
              <div class="flex justify-between items-center mt-2">
                <p class="text-xs text-muted-foreground flex-1">
                  注意：修改提示词会直接影响 AI 生成的内容质量。请确保您熟悉 Markdown 与系统预留的 {变量} 占位符。
                </p>
                <Button @click="updateSetting(setting)" size="sm">
                  <Save class="w-4 h-4 mr-2" />
                  保存并生效
                </Button>
              </div>
            </div>
          </AccordionContent>
        </AccordionItem>
      </Accordion>

      <div v-if="promptSettings.length === 0" class="flex flex-col items-center justify-center p-12 text-center border rounded-xl bg-card border-dashed">
        <MessageSquareText class="w-8 h-8 text-muted-foreground/50 mb-4" />
        <h3 class="text-lg font-medium">暂无提示词模板</h3>
        <p class="text-sm text-muted-foreground mt-1">系统没有暴露需要配置的 AI 提示词</p>
      </div>
    </div>
  </div>
</template>
