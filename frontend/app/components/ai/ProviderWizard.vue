<script setup lang="ts">
import { ArrowLeft, CheckCircle2, KeyRound, Loader2, Settings2, XCircle } from '@lucide/vue'
import { toast } from 'vue-sonner'
import type { AIConfigScope, AIModelInput, AIProvider, InterfaceType } from '~/types/ai-config'
import { PROVIDER_PRESETS, INTERFACE_LABELS, type ProviderPreset } from '~/lib/ai-config'
import ModelPicker from '~/components/ai/ModelPicker.vue'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

const props = defineProps<{ scope: AIConfigScope }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ created: [provider: AIProvider] }>()

const api = useAIConfigApi(props.scope)

type Step = 'preset' | 'credentials' | 'models'
const step = ref<Step>('preset')
const form = ref({ name: '', interface_type: 'openai' as InterfaceType, base_url: '', api_key: '' })
const isCustom = ref(false)
const showAdvanced = ref(false)
const testing = ref(false)
const testResult = ref<{ ok: boolean, message: string } | null>(null)
const candidates = ref<AIModelInput[]>([])
const selectedModels = ref<AIModelInput[]>([])
const saving = ref(false)

const reset = () => {
  step.value = 'preset'
  form.value = { name: '', interface_type: 'openai', base_url: '', api_key: '' }
  isCustom.value = false
  showAdvanced.value = false
  testResult.value = null
  candidates.value = []
  selectedModels.value = []
}

watch(open, (v) => { if (v) reset() })

const choosePreset = (preset: ProviderPreset | null) => {
  isCustom.value = !preset
  showAdvanced.value = !preset
  form.value.name = preset?.name ?? ''
  form.value.interface_type = preset?.interface_type ?? 'openai'
  form.value.base_url = preset?.base_url ?? ''
  step.value = 'credentials'
}

const canTest = computed(() => !!form.value.name.trim() && !!form.value.api_key.trim())

const testAndDiscover = async () => {
  testing.value = true
  testResult.value = null
  try {
    const res = await api.discover({
      interface_type: form.value.interface_type,
      base_url: form.value.base_url || null,
      api_key: form.value.api_key,
    })
    testResult.value = { ok: res.ok, message: res.message }
    if (res.ok) {
      candidates.value = res.models
      step.value = 'models'
    }
  } catch (e) {
    testResult.value = { ok: false, message: apiErrorMessage(e) }
  } finally {
    testing.value = false
  }
}

const continueManually = () => {
  candidates.value = []
  step.value = 'models'
}

const finish = async () => {
  if (!selectedModels.value.length) {
    toast.error('请至少选择一个模型')
    return
  }
  saving.value = true
  try {
    const provider = await api.createProvider({
      name: form.value.name.trim(),
      interface_type: form.value.interface_type,
      base_url: form.value.base_url || undefined,
      api_key: form.value.api_key,
      is_active: true,
      models: selectedModels.value,
    })
    open.value = false
    emit('created', provider)
  } catch (e) {
    toast.error('添加失败', { description: apiErrorMessage(e) })
  } finally {
    saving.value = false
  }
}

const stepIndex = computed(() => ({ preset: 1, credentials: 2, models: 3 }[step.value]))
</script>

<template>
  <Dialog v-model:open="open">
    <DialogContent class="sm:max-w-xl">
      <DialogHeader>
        <DialogTitle>添加服务商</DialogTitle>
        <DialogDescription>
          第 {{ stepIndex }} / 3 步：
          {{ step === 'preset' ? '选择服务商' : step === 'credentials' ? '填写 API Key 并测试连接' : '选择要使用的模型' }}
        </DialogDescription>
      </DialogHeader>

      <!-- Step 1: preset -->
      <div v-if="step === 'preset'" class="grid gap-2 sm:grid-cols-2">
        <button
          v-for="preset in PROVIDER_PRESETS"
          :key="preset.id"
          type="button"
          class="rounded-lg border p-3 text-left transition-colors hover:border-primary hover:bg-muted/40"
          @click="choosePreset(preset)"
        >
          <div class="font-medium">{{ preset.name }}</div>
          <div class="mt-0.5 text-xs text-muted-foreground">{{ preset.hint }}</div>
        </button>
        <button
          type="button"
          class="rounded-lg border border-dashed p-3 text-left transition-colors hover:border-primary hover:bg-muted/40"
          @click="choosePreset(null)"
        >
          <div class="font-medium">其他 / 自定义</div>
          <div class="mt-0.5 text-xs text-muted-foreground">任何兼容 OpenAI 接口的服务，或自建中转</div>
        </button>
      </div>

      <!-- Step 2: credentials -->
      <form v-else-if="step === 'credentials'" class="grid gap-4" @submit.prevent="canTest && testAndDiscover()">
        <div class="grid gap-2">
          <Label for="wiz-name">名称</Label>
          <Input id="wiz-name" v-model="form.name" placeholder="便于自己识别，例如：我的 DeepSeek" />
        </div>
        <div class="grid gap-2">
          <Label for="wiz-key">API Key</Label>
          <div class="relative">
            <KeyRound class="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input id="wiz-key" v-model="form.api_key" type="password" autocomplete="off" placeholder="sk-..." class="pl-9" />
          </div>
          <p v-if="scope === 'personal'" class="text-xs text-muted-foreground">Key 加密保存，仅用于你本人的 AI 请求，管理员也无法查看。</p>
          <p v-else class="text-xs text-muted-foreground">Key 加密保存，全站用户共用此服务商的额度。</p>
        </div>

        <button
          v-if="!isCustom"
          type="button"
          class="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          @click="showAdvanced = !showAdvanced"
        >
          <Settings2 class="h-3.5 w-3.5" />{{ showAdvanced ? '收起高级设置' : '高级设置（接口地址）' }}
        </button>
        <template v-if="showAdvanced">
          <div class="grid gap-2">
            <Label>接口类型</Label>
            <Select v-model="form.interface_type">
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="openai">{{ INTERFACE_LABELS.openai }}（大多数服务商）</SelectItem>
                <SelectItem value="gemini">{{ INTERFACE_LABELS.gemini }}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div class="grid gap-2">
            <Label for="wiz-url">接口地址（Base URL）</Label>
            <Input id="wiz-url" v-model="form.base_url" :placeholder="form.interface_type === 'gemini' ? '留空使用官方地址' : '例如 https://api.deepseek.com/v1'" />
          </div>
        </template>

        <div
          v-if="testResult && !testResult.ok"
          class="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive"
        >
          <XCircle class="mt-0.5 h-4 w-4 shrink-0" />
          <div class="flex-1">
            <div>连接失败：{{ testResult.message }}</div>
            <button type="button" class="mt-1 text-xs underline text-muted-foreground" @click="continueManually">
              部分服务商不提供模型列表，确认无误可跳过，手动填写模型
            </button>
          </div>
        </div>
      </form>

      <!-- Step 3: models -->
      <div v-else class="space-y-3">
        <div v-if="testResult?.ok" class="flex items-center gap-2 text-sm text-green-600">
          <CheckCircle2 class="h-4 w-4" />{{ testResult.message }}
        </div>
        <ModelPicker v-model="selectedModels" :candidates="candidates" />
      </div>

      <DialogFooter class="gap-2 sm:justify-between">
        <Button
          v-if="step !== 'preset'"
          variant="ghost"
          @click="step = step === 'models' ? 'credentials' : 'preset'"
        >
          <ArrowLeft class="mr-1 h-4 w-4" />上一步
        </Button>
        <span v-else />
        <Button v-if="step === 'credentials'" :disabled="!canTest || testing" @click="testAndDiscover">
          <Loader2 v-if="testing" class="mr-2 h-4 w-4 animate-spin" />
          测试连接并获取模型
        </Button>
        <Button v-else-if="step === 'models'" :disabled="saving || !selectedModels.length" @click="finish">
          <Loader2 v-if="saving" class="mr-2 h-4 w-4 animate-spin" />
          完成添加
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
</template>
