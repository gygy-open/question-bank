import { getApiErrorCodeMessage } from '@/lib/apiErrors'
import { translate } from '@/lib/locale'
import type {
  AIConfigScope,
  AIModel,
  AIModelInput,
  AIProvider,
  AIProviderCreate,
  AIProviderUpdate,
  DiscoverModelsResponse,
} from '~/types/ai-config'

export const apiErrorMessage = (error: any): string => {
  const coded = getApiErrorCodeMessage(error)
  if (coded) return coded
  const detail = error?.data?.detail ?? error?.response?._data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg
  return error?.message ?? translate('common.unknownError')
}

export const apiErrorStatus = (error: any): number | undefined =>
  error?.response?.status ?? error?.statusCode ?? error?.status

/**
 * 全局（管理员）与个人服务商的接口路径完全对称：
 * /ai-config/providers… 与 /ai-config/me/providers…
 */
export const useAIConfigApi = (scope: AIConfigScope) => {
  const { $api } = useNuxtApp()
  const base = scope === 'global' ? '/ai-config' : '/ai-config/me'

  return {
    createProvider: (body: AIProviderCreate) =>
      $api<AIProvider>(`${base}/providers`, { method: 'POST', body }),
    updateProvider: (id: number, body: AIProviderUpdate) =>
      $api<AIProvider>(`${base}/providers/${id}`, { method: 'PUT', body }),
    deleteProvider: (id: number, force = false) =>
      $api(`${base}/providers/${id}`, { method: 'DELETE', query: force ? { force: true } : undefined }),
    addModel: (providerId: number, body: AIModelInput) =>
      $api<AIModel>(`${base}/providers/${providerId}/models`, { method: 'POST', body }),
    updateModel: (id: number, body: Partial<AIModelInput>) =>
      $api<AIModel>(`${base}/models/${id}`, { method: 'PUT', body }),
    deleteModel: (id: number, force = false) =>
      $api(`${base}/models/${id}`, { method: 'DELETE', query: force ? { force: true } : undefined }),
    discover: (body: { interface_type?: string, base_url?: string | null, api_key?: string, provider_id?: number }) =>
      $api<DiscoverModelsResponse>('/ai-config/discover-models', { method: 'POST', body, query: { scope } }),
  }
}
