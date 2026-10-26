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

const { t } = useI18n()
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
  emptyLabel: t('aiModels.followGlobal'),
  fallbackLabel: globalLabel(scene),
  description: scene === 'text'
    ? t('aiSettings.my.textDescription')
    : t('aiSettings.my.visionDescription'),
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
    toast.error(t('aiSettings.toast.loadFailedShort'), { description: apiErrorMessage(e) })
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
    toast.success(t('common.saved'))
  } catch (e) {
    toast.error(t('common.saveFailed'), { description: apiErrorMessage(e) })
  } finally {
    saving.value = false
  }
}

/** 用户加自己的服务商，多半就是想用它：预选为默认，由用户确认保存。 */
const onCreated = async (provider: AIProvider) => {
  toast.success(t('aiSettings.toast.providerAdded', { name: provider.name }))
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
    toast.info(t('aiSettings.toast.prefilledMine'))
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
        <h3 class="text-lg font-semibold">{{ t('aiSettings.my.defaultTitle') }}</h3>
        <p class="text-sm text-muted-foreground">{{ t('aiSettings.my.defaultDescription') }}</p>
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
      <p class="mt-2 text-xs text-muted-foreground">{{ t('aiSettings.my.embeddingNote') }}</p>
    </section>

    <section>
      <div class="mb-3 flex items-end justify-between gap-4">
        <div>
          <h3 class="text-lg font-semibold">{{ t('aiSettings.my.providersTitle') }}</h3>
          <p class="text-sm text-muted-foreground">{{ t('aiSettings.my.providersDescription') }}</p>
        </div>
        <Button v-if="myProviders.length" @click="wizardOpen = true">
          <Plus class="mr-2 h-4 w-4" />{{ t('aiProviders.add') }}
        </Button>
      </div>

      <Empty v-if="!myProviders.length" class="border border-dashed">
        <EmptyHeader>
          <EmptyMedia variant="icon"><KeyRound /></EmptyMedia>
          <EmptyTitle>{{ t('aiSettings.my.emptyTitle') }}</EmptyTitle>
          <EmptyDescription>
            {{ t('aiSettings.my.emptyDescription') }}
          </EmptyDescription>
        </EmptyHeader>
        <EmptyContent>
          <Button variant="outline" @click="wizardOpen = true"><Plus class="mr-2 h-4 w-4" />{{ t('aiSettings.my.connect') }}</Button>
        </EmptyContent>
      </Empty>
      <ProviderList v-else :providers="myProviders" scope="personal" :usage="usage" @changed="fetchData" />
    </section>

    <ProviderWizard v-model:open="wizardOpen" scope="personal" @created="onCreated" />
  </div>
</template>
