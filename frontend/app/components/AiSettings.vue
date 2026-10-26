<script setup lang="ts">
import { Loader2, Plus, Server } from '@lucide/vue'
import { toast } from 'vue-sonner'
import type { ActiveAIConfig, AIProvider } from '~/types/ai-config'
import type { ReindexResult } from '~/types'
import { flattenModels, modelsForScene, usageMap, type Scene } from '~/lib/ai-config'
import ModelAssignmentPanel, { type AssignmentRow } from '~/components/ai/ModelAssignmentPanel.vue'
import ProviderList from '~/components/ai/ProviderList.vue'
import ProviderWizard from '~/components/ai/ProviderWizard.vue'
import ConfirmDialog from '~/components/ai/ConfirmDialog.vue'
import { Button } from '@/components/ui/button'
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'

const { $api } = useNuxtApp()
const { notifyAIConfigChanged } = useGlobalChat()

type Assignment = Partial<Record<Scene, number | null>>

const allProviders = ref<AIProvider[]>([])
const saved = ref<Assignment>({ text: null, vision: null, embedding: null })
const draft = ref<Assignment>({ ...saved.value })
const loading = ref(true)
const saving = ref(false)
const wizardOpen = ref(false)
const confirmRef = ref<InstanceType<typeof ConfirmDialog> | null>(null)

const globalProviders = computed(() => allProviders.value.filter(p => !p.is_personal))
const personalProviders = computed(() => allProviders.value.filter(p => p.is_personal))
const globalModels = computed(() => flattenModels(globalProviders.value))
const usage = computed(() => usageMap(saved.value))

const rows = computed<AssignmentRow[]>(() => (['text', 'vision', 'embedding'] as Scene[]).map(scene => ({
  scene,
  options: modelsForScene(globalModels.value, scene),
  emptyLabel: '不设置',
})))

const fromActive = (c: ActiveAIConfig): Assignment => ({
  text: c.text_model_id, vision: c.vision_model_id, embedding: c.embedding_model_id,
})

const fetchData = async () => {
  try {
    const [providers, active] = await Promise.all([
      $api<AIProvider[]>('/ai-config/providers', { query: { include_personal: true } }),
      $api<ActiveAIConfig>('/ai-config/active-config'),
    ])
    allProviders.value = providers
    notifyAIConfigChanged()
    const wasDirty = JSON.stringify(draft.value) !== JSON.stringify(saved.value)
    saved.value = fromActive(active)
    if (!wasDirty) draft.value = { ...saved.value }
  } catch (e) {
    toast.error('加载配置失败', { description: apiErrorMessage(e) })
  } finally {
    loading.value = false
  }
}

const reindex = async () => {
  const id = toast.loading('正在重建向量索引…')
  try {
    const res = await $api<ReindexResult>('/knowledge-points/reindex-vectors', { method: 'POST' })
    toast.success(`向量索引已重建（${res.reindexed} 条，用时 ${res.duration}s）`, { id })
  } catch (e) {
    toast.error('重建索引失败', { id, description: `${apiErrorMessage(e)}。可稍后在“知识点”页面重试。` })
  }
}

const save = async () => {
  let rebuild = false
  const embeddingChanged = (draft.value.embedding ?? null) !== (saved.value.embedding ?? null)
  if (embeddingChanged && draft.value.embedding != null) {
    const r = await confirmRef.value?.ask({
      title: '更换向量模型',
      description: '不同向量模型生成的索引互不兼容。更换后需要重建知识点索引，否则相似题检索和知识点匹配会失效。\n重建会调用新模型处理所有知识点，可能需要一些时间。',
      confirmLabel: '保存并重建索引',
      altLabel: '仅保存',
    })
    if (!r || r === 'cancel') return
    rebuild = r === 'confirm'
  }

  saving.value = true
  try {
    await $api('/ai-config/active-config', {
      method: 'POST',
      body: {
        text_model_id: draft.value.text ?? null,
        vision_model_id: draft.value.vision ?? null,
        embedding_model_id: draft.value.embedding ?? null,
      },
    })
    saved.value = { ...draft.value }
    notifyAIConfigChanged()
    toast.success('已保存')
  } catch (e) {
    toast.error('保存失败', { description: apiErrorMessage(e) })
    return
  } finally {
    saving.value = false
  }
  if (rebuild) await reindex()
}

/** 新服务商加好后，为还没配置的场景预选模型（只改草稿，由管理员确认保存）。 */
const onCreated = async (provider: AIProvider) => {
  toast.success(`已添加“${provider.name}”`)
  await fetchData()
  const fresh = flattenModels([provider])
  const picks: string[] = []
  const next = { ...draft.value }
  for (const scene of ['text', 'vision', 'embedding'] as Scene[]) {
    if (next[scene] != null) continue
    const m = modelsForScene(fresh, scene)[0]
    if (m) {
      next[scene] = m.id
      picks.push(scene)
    }
  }
  if (picks.length) {
    draft.value = next
    toast.info('已为未配置的场景预选了模型，请在上方确认后保存')
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
        <h3 class="text-lg font-semibold">当前在用</h3>
        <p class="text-sm text-muted-foreground">各项功能默认使用的模型，对所有用户生效。用户也可以在“我的 AI 模型”里改用自己的服务商。</p>
      </div>
      <ModelAssignmentPanel
        v-model="draft"
        :rows="rows"
        :all-models="globalModels"
        :saved="saved"
        :saving="saving"
        @save="save"
        @reset="draft = { ...saved }"
      />
    </section>

    <section>
      <div class="mb-3 flex items-end justify-between gap-4">
        <div>
          <h3 class="text-lg font-semibold">全局服务商</h3>
          <p class="text-sm text-muted-foreground">由管理员维护，所有用户都可以使用。</p>
        </div>
        <Button v-if="globalProviders.length" @click="wizardOpen = true">
          <Plus class="mr-2 h-4 w-4" />添加服务商
        </Button>
      </div>

      <Empty v-if="!globalProviders.length" class="border border-dashed">
        <EmptyHeader>
          <EmptyMedia variant="icon"><Server /></EmptyMedia>
          <EmptyTitle>还没有接入 AI 服务商</EmptyTitle>
          <EmptyDescription>接入后即可使用 AI 对话、文档题目抽取、图片识别和知识点匹配。</EmptyDescription>
        </EmptyHeader>
        <EmptyContent>
          <Button @click="wizardOpen = true"><Plus class="mr-2 h-4 w-4" />添加服务商</Button>
        </EmptyContent>
      </Empty>
      <ProviderList v-else :providers="globalProviders" scope="global" :usage="usage" @changed="fetchData" />
    </section>

    <section v-if="personalProviders.length">
      <div class="mb-3">
        <h3 class="text-lg font-semibold">用户个人服务商</h3>
        <p class="text-sm text-muted-foreground">用户自行接入、仅供本人使用。你可以查看和删除，但看不到 API Key。</p>
      </div>
      <ProviderList :providers="personalProviders" scope="global" review @changed="fetchData" />
    </section>

    <ProviderWizard v-model:open="wizardOpen" scope="global" @created="onCreated" />
    <ConfirmDialog ref="confirmRef" />
  </div>
</template>
