import type { AIModel, AIProvider, InterfaceType } from '@/types/ai-config'

export interface ProviderPreset {
  id: string
  name: string
  interface_type: InterfaceType
  base_url: string
  hint: string
}

export const PROVIDER_PRESETS: ProviderPreset[] = [
  { id: 'deepseek', name: 'DeepSeek', interface_type: 'openai', base_url: 'https://api.deepseek.com/v1', hint: '性价比高，适合题目抽取与对话' },
  { id: 'qwen', name: '通义千问', interface_type: 'openai', base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', hint: '含识图模型（qwen-vl）与向量模型' },
  { id: 'zhipu', name: '智谱 GLM', interface_type: 'openai', base_url: 'https://open.bigmodel.cn/api/paas/v4', hint: '含识图模型（glm-4v）' },
  { id: 'kimi', name: 'Kimi', interface_type: 'openai', base_url: 'https://api.moonshot.cn/v1', hint: '长文档友好' },
  { id: 'openai', name: 'OpenAI', interface_type: 'openai', base_url: 'https://api.openai.com/v1', hint: '需可访问海外网络' },
  { id: 'gemini', name: 'Google Gemini', interface_type: 'gemini', base_url: '', hint: '需可访问海外网络，原生支持识图' },
]

export const INTERFACE_LABELS: Record<string, string> = {
  openai: 'OpenAI 兼容接口',
  gemini: 'Gemini 接口',
}

export type Scene = 'text' | 'vision' | 'embedding'

export const SCENES: Record<Scene, { label: string, description: string }> = {
  text: { label: '文本模型', description: '用于 AI 对话、文档题目抽取、知识点匹配。' },
  vision: { label: '识图模型', description: '用于从图片、截图中识别题目。需要支持识图的模型。' },
  embedding: { label: '向量模型', description: '用于相似题检索和知识点语义匹配，全站共用。' },
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
    map.set(id, [...(map.get(id) ?? []), SCENES[scene].label])
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
