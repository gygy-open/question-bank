export type InterfaceType = 'openai' | 'gemini'

export interface AIModel {
  id: number
  provider_id: number
  name: string
  is_vision_capable: boolean
  is_embedding_model: boolean
}

/** 后端从不回显 API Key，只返回 api_key_set。 */
export interface AIProvider {
  id: number
  name: string
  interface_type: InterfaceType
  base_url?: string | null
  is_active: boolean
  owner_id: number | null
  owner_name?: string | null
  is_personal: boolean
  api_key_set: boolean
  models: AIModel[]
}

export interface AIModelInput {
  name: string
  is_vision_capable: boolean
  is_embedding_model: boolean
}

export interface AIProviderCreate {
  name: string
  interface_type: InterfaceType
  base_url?: string
  api_key: string
  is_active?: boolean
  models?: AIModelInput[]
}

export interface AIProviderUpdate {
  name?: string
  interface_type?: InterfaceType
  base_url?: string
  api_key?: string
  is_active?: boolean
}

export interface ActiveAIConfig {
  text_model_id: number | null
  vision_model_id: number | null
  embedding_model_id: number | null
}

export interface DiscoverModelsResponse {
  ok: boolean
  message: string
  models: AIModelInput[]
}

export interface EffectiveModel {
  model_id: number | null
  source: 'personal' | 'global' | null
  error: string | null
}

export interface UserAIPreference {
  text_model_id: number | null
  vision_model_id: number | null
  effective_text: EffectiveModel
  effective_vision: EffectiveModel
}

/** 区分全局（管理员维护）与个人服务商的 API 前缀。 */
export type AIConfigScope = 'global' | 'personal'
