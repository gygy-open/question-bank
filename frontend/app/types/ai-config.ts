export interface AIModel {
  id: number
  provider_id: number
  name: string
  is_vision_capable: boolean
  is_embedding_model: boolean
}

export interface AIProvider {
  id: number
  name: string
  interface_type: 'openai' | 'gemini'
  base_url?: string
  api_key: string
  is_active: boolean
  models: AIModel[]
}

export interface AIProviderCreate {
  name: string
  interface_type: 'openai' | 'gemini'
  base_url?: string
  api_key: string
  is_active?: boolean
  models?: { name: string; is_vision_capable: boolean; is_embedding_model: boolean }[]
}

export interface AIProviderUpdate {
  name?: string
  interface_type?: 'openai' | 'gemini'
  base_url?: string
  api_key?: string
  is_active?: boolean
}

export interface ActiveAIConfig {
  text_model_id: number | null
  vision_model_id: number | null
  embedding_model_id: number | null
}
