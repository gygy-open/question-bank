import type { AIModel, AIProvider, InterfaceType } from '@/types/ai-config'
import { translate } from '@/lib/locale'

/** 展示文案存 i18n key（nameKey / hintKey），使用处再 t()。 */
export interface ProviderPreset {
  id: string
  /** 品牌名；有 nameKey 时以翻译为准 */
  name: string
  nameKey?: string
  interface_type: InterfaceType
  base_url: string
  hintKey: string
}

export const PROVIDER_PRESETS: ProviderPreset[] = [
  { id: 'deepseek', name: 'DeepSeek', interface_type: 'openai', base_url: 'https://api.deepseek.com/v1', hintKey: 'aiProviders.presets.deepseek.hint' },
  { id: 'qwen', name: 'Qwen', nameKey: 'aiProviders.presets.qwen.name', interface_type: 'openai', base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', hintKey: 'aiProviders.presets.qwen.hint' },
  { id: 'zhipu', name: 'Zhipu GLM', nameKey: 'aiProviders.presets.zhipu.name', interface_type: 'openai', base_url: 'https://open.bigmodel.cn/api/paas/v4', hintKey: 'aiProviders.presets.zhipu.hint' },
  { id: 'kimi', name: 'Kimi', interface_type: 'openai', base_url: 'https://api.moonshot.cn/v1', hintKey: 'aiProviders.presets.kimi.hint' },
  { id: 'openai', name: 'OpenAI', interface_type: 'openai', base_url: 'https://api.openai.com/v1', hintKey: 'aiProviders.presets.openai.hint' },
  { id: 'gemini', name: 'Google Gemini', interface_type: 'gemini', base_url: '', hintKey: 'aiProviders.presets.gemini.hint' },
]

/** interface_type → 显示名的 i18n key */
export const INTERFACE_LABEL_KEYS: Record<string, string> = {
  openai: 'aiProviders.interfaceTypes.openai',
  gemini: 'aiProviders.interfaceTypes.gemini',
}

export type Scene = 'text' | 'vision' | 'embedding'

/** 场景 → 显示名 / 说明的 i18n key */
export const SCENES: Record<Scene, { labelKey: string, descriptionKey: string }> = {
  text: { labelKey: 'aiModels.scenes.text.label', descriptionKey: 'aiModels.scenes.text.description' },
  vision: { labelKey: 'aiModels.scenes.vision.label', descriptionKey: 'aiModels.scenes.vision.description' },
  embedding: { labelKey: 'aiModels.scenes.embedding.label', descriptionKey: 'aiModels.scenes.embedding.description' },
}

export interface FlatModel extends AIModel {
  providerName: string
  providerActive: boolean
  isPersonal: boolean
  label: string
}

export const flattenModels = (providers: AIProvider[]): FlatModel[] =>
  providers.flatMap(p => p.models.map(m => ({
    ...m,
    providerName: p.name,
    providerActive: p.is_active,
    isPersonal: p.is_personal,
    label: `${p.name} / ${m.name}`,
  })))

/** 某个场景下可选的模型：服务商需启用，且能力匹配。 */
export const modelsForScene = (models: FlatModel[], scene: Scene): FlatModel[] =>
  models.filter((m) => {
    if (!m.providerActive) return false
    if (scene === 'embedding') return m.is_embedding_model
    if (m.is_embedding_model) return false
    return scene === 'vision' ? m.is_vision_capable : true
  })

export type SceneState = 'ok' | 'unset' | 'unavailable'

export const sceneState = (models: FlatModel[], scene: Scene, modelId: number | null | undefined): SceneState => {
  if (modelId == null) return 'unset'
  return modelsForScene(models, scene).some(m => m.id === modelId) ? 'ok' : 'unavailable'
}

/** modelId → 正在使用它的场景名，用于在模型列表上标出“使用中”。 */
export const usageMap = (assignments: Partial<Record<Scene, number | null>>): Map<number, string[]> => {
  const map = new Map<number, string[]>()
  for (const [scene, id] of Object.entries(assignments) as [Scene, number | null][]) {
    if (id == null) continue
    map.set(id, [...(map.get(id) ?? []), translate(SCENES[scene].labelKey)])
  }
  return map
}

/**
 * 聊天框该选中哪个模型。
 * - 默认模型变了（改了个人偏好或全局设置）→ 切到新的默认模型；
 * - 当前选择已不可用 → 回到默认模型，没有则取第一个；
 * - 否则保留用户在聊天框里的手动选择。
 */
export const pickChatModel = (
  availableIds: number[],
  currentId: number | null,
  defaultId: number | null,
  previousDefaultId: number | null | undefined,
): number | null => {
  const defaultAvailable = defaultId != null && availableIds.includes(defaultId)
  const currentAvailable = currentId != null && availableIds.includes(currentId)
  if (defaultAvailable && (defaultId !== previousDefaultId || !currentAvailable)) return defaultId
  if (currentAvailable) return currentId
  return availableIds[0] ?? null
}
