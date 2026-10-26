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

const { t } = useI18n()
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
  emptyLabel: t('aiModels.unset'),
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
    toast.error(t('aiSettings.toast.loadFailed'), { description: apiErrorMessage(e) })
  } finally {
    loading.value = false
  }
}

const reindex = async () => {
  const id = toast.loading(t('aiSettings.toast.reindexing'))
  try {
    const res = await $api<ReindexResult>('/knowledge-points/reindex-vectors', { method: 'POST' })
    toast.success(t('aiSettings.toast.reindexed', { count: res.reindexed, duration: res.duration }), { id })
  } catch (e) {
    toast.error(t('aiSettings.toast.reindexFailed'), { id, description: t('aiSettings.toast.reindexFailedDescription', { error: apiErrorMessage(e) }) })
  }
}

const save = async () => {
  let rebuild = false
  const embeddingChanged = (draft.value.embedding ?? null) !== (saved.value.embedding ?? null)
  if (embeddingChanged && draft.value.embedding != null) {
    const r = await confirmRef.value?.ask({
      title: t('aiSettings.changeEmbedding.title'),
      description: t('aiSettings.changeEmbedding.description'),
      confirmLabel: t('aiSettings.changeEmbedding.confirm'),
      altLabel: t('aiSettings.changeEmbedding.saveOnly'),
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
    toast.success(t('common.saved'))
  } catch (e) {
    toast.error(t('common.saveFailed'), { description: apiErrorMessage(e) })
    return
  } finally {
    saving.value = false
  }
  if (rebuild) await reindex()
}

/** 新服务商加好后，为还没配置的场景预选模型（只改草稿，由管理员确认保存）。 */
const onCreated = async (provider: AIProvider) => {
  toast.success(t('aiSettings.toast.providerAdded', { name: provider.name }))
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
    toast.info(t('aiSettings.toast.prefilled'))
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
        <h3 class="text-lg font-semibold">{{ t('aiSettings.current.title') }}</h3>
        <p class="text-sm text-muted-foreground">{{ t('aiSettings.current.globalDescription') }}</p>
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
          <h3 class="text-lg font-semibold">{{ t('aiSettings.globalProviders.title') }}</h3>
          <p class="text-sm text-muted-foreground">{{ t('aiSettings.globalProviders.description') }}</p>
        </div>
        <Button v-if="globalProviders.length" @click="wizardOpen = true">
          <Plus class="mr-2 h-4 w-4" />{{ t('aiProviders.add') }}
        </Button>
      </div>

      <Empty v-if="!globalProviders.length" class="border border-dashed">
        <EmptyHeader>
          <EmptyMedia variant="icon"><Server /></EmptyMedia>
          <EmptyTitle>{{ t('aiSettings.empty.title') }}</EmptyTitle>
          <EmptyDescription>{{ t('aiSettings.empty.description') }}</EmptyDescription>
        </EmptyHeader>
        <EmptyContent>
          <Button @click="wizardOpen = true"><Plus class="mr-2 h-4 w-4" />{{ t('aiProviders.add') }}</Button>
        </EmptyContent>
      </Empty>
      <ProviderList v-else :providers="globalProviders" scope="global" :usage="usage" @changed="fetchData" />
    </section>

    <section v-if="personalProviders.length">
      <div class="mb-3">
        <h3 class="text-lg font-semibold">{{ t('aiSettings.userProviders.title') }}</h3>
        <p class="text-sm text-muted-foreground">{{ t('aiSettings.userProviders.description') }}</p>
      </div>
      <ProviderList :providers="personalProviders" scope="global" review @changed="fetchData" />
    </section>

    <ProviderWizard v-model:open="wizardOpen" scope="global" @created="onCreated" />
    <ConfirmDialog ref="confirmRef" />
  </div>
</template>
