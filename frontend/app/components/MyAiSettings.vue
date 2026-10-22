<script setup lang="ts">
import { KeyRound, Loader2, Plus } from '@lucide/vue'
import { toast } from 'vue-sonner'
import type { ActiveAIConfig, AIProvider, UserAIPreference } from '~/types/ai-config'
import { flattenModels, modelsForScene, usageMap, type Scene } from '~/lib/ai-config'
import ModelAssignmentPanel, { type AssignmentRow } from '~/components/ai/ModelAssignmentPanel.vue'
import ProviderList from '~/components/ai/ProviderList.vue'
import ProviderWizard from '~/components/ai/ProviderWizard.vue'
import { Button } from '@/components/ui/button'
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'

const { $api } = useNuxtApp()
const { notifyAIConfigChanged } = useGlobalChat()

type Assignment = Partial<Record<Scene, number | null>>
const SCENES_HERE: Scene[] = ['text', 'vision']

const providers = ref<AIProvider[]>([])
const globalActive = ref<ActiveAIConfig | null>(null)
const saved = ref<Assignment>({ text: null, vision: null })
const draft = ref<Assignment>({ text: null, vision: null })
const loading = ref(true)
const saving = ref(false)
const wizardOpen = ref(false)

const myProviders = computed(() => providers.value.filter(p => p.is_personal))
const models = computed(() => flattenModels(providers.value))
const usage = computed(() => usageMap(saved.value))

const globalLabel = (scene: Scene): string | null => {
  const id = scene === 'text' ? globalActive.value?.text_model_id : globalActive.value?.vision_model_id
  const m = modelsForScene(models.value.filter(x => !x.isPersonal), scene).find(x => x.id === id)
  return m?.label ?? null
}

const rows = computed<AssignmentRow[]>(() => SCENES_HERE.map(scene => ({
  scene,
  options: modelsForScene(models.value, scene),
  emptyLabel: '跟随全局默认',
  fallbackLabel: globalLabel(scene),
  description: scene === 'text'
    ? '你的 AI 对话默认模型，以及你发起的文档导入、知识点匹配所用的模型。'
    : '你上传图片识别题目时使用的模型。',
})))

const fromPref = (p: UserAIPreference): Assignment => ({ text: p.text_model_id, vision: p.vision_model_id })

const fetchData = async () => {
  try {
    const [list, pref, active] = await Promise.all([
      $api<AIProvider[]>('/ai-config/providers'),
      $api<UserAIPreference>('/ai-config/me/preferences'),
      $api<ActiveAIConfig>('/ai-config/active-config'),
    ])
    providers.value = list
    notifyAIConfigChanged()
    globalActive.value = active
    const wasDirty = JSON.stringify(draft.value) !== JSON.stringify(saved.value)
    saved.value = fromPref(pref)
    if (!wasDirty) draft.value = { ...saved.value }
  } catch (e) {
    toast.error('加载失败', { description: apiErrorMessage(e) })
  } finally {
    loading.value = false
  }
}

const save = async () => {
  saving.value = true
  try {
    const pref = await $api<UserAIPreference>('/ai-config/me/preferences', {
      method: 'PUT',
      body: { text_model_id: draft.value.text ?? null, vision_model_id: draft.value.vision ?? null },
    })
    saved.value = fromPref(pref)
    draft.value = { ...saved.value }
    notifyAIConfigChanged()
    toast.success('已保存')
  } catch (e) {
    toast.error('保存失败', { description: apiErrorMessage(e) })
  } finally {
    saving.value = false
  }
}

/** 用户加自己的服务商，多半就是想用它：预选为默认，由用户确认保存。 */
const onCreated = async (provider: AIProvider) => {
  toast.success(`已添加“${provider.name}”`)
  await fetchData()
  const fresh = flattenModels([provider])
  const next = { ...draft.value }
  let picked = false
  for (const scene of SCENES_HERE) {
    if (next[scene] != null) continue
    const m = modelsForScene(fresh, scene)[0]
    if (m) {
      next[scene] = m.id
      picked = true
    }
  }
  if (picked) {
    draft.value = next
    toast.info('已预选为你的默认模型，请在上方确认后保存')
  }
}

onMounted(fetchData)
</script>

<template>
  <div v-if="loading" class="flex justify-center py-12">
    <Loader2 class="h-6 w-6 animate-spin text-muted-foreground" />
  </div>

  <div v-else class="space-y-10">
    <section>
      <div class="mb-3">
        <h3 class="text-lg font-semibold">我的默认模型</h3>
        <p class="text-sm text-muted-foreground">默认跟随管理员的全局设置。也可以改选其他全局模型，或你自己接入的模型。只影响你本人。</p>
      </div>
      <ModelAssignmentPanel
        v-model="draft"
        :rows="rows"
        :all-models="models"
        :saved="saved"
        :saving="saving"
        @save="save"
        @reset="draft = { ...saved }"
      />
      <p class="mt-2 text-xs text-muted-foreground">相似题检索使用的向量模型由管理员统一设置。</p>
    </section>

    <section>
      <div class="mb-3 flex items-end justify-between gap-4">
        <div>
          <h3 class="text-lg font-semibold">我的服务商</h3>
          <p class="text-sm text-muted-foreground">使用你自己的 API Key，费用计入你自己的账户。</p>
        </div>
        <Button v-if="myProviders.length" @click="wizardOpen = true">
          <Plus class="mr-2 h-4 w-4" />添加服务商
        </Button>
      </div>

      <Empty v-if="!myProviders.length" class="border border-dashed">
        <EmptyHeader>
          <EmptyMedia variant="icon"><KeyRound /></EmptyMedia>
          <EmptyTitle>还没有自己的服务商</EmptyTitle>
          <EmptyDescription>
            不添加也可以直接使用管理员配置的模型。如果想用自己的账号（例如自己购买的 DeepSeek 额度或更强的模型），可以在这里接入。
          </EmptyDescription>
        </EmptyHeader>
        <EmptyContent>
          <Button variant="outline" @click="wizardOpen = true"><Plus class="mr-2 h-4 w-4" />接入我的服务商</Button>
        </EmptyContent>
      </Empty>
      <ProviderList v-else :providers="myProviders" scope="personal" :usage="usage" @changed="fetchData" />
    </section>

    <ProviderWizard v-model:open="wizardOpen" scope="personal" @created="onCreated" />
  </div>
</template>
