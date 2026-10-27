import { translate } from '@/lib/locale'

export function getApiErrorStatus(error: unknown): number | undefined {
  const candidate = error as { statusCode?: number, status?: number, response?: { status?: number } }
  return candidate?.statusCode ?? candidate?.status ?? candidate?.response?.status
}

export function isRevisionConflict(error: unknown): boolean {
  return getApiErrorStatus(error) === 409
}

type ApiErrorBody = { detail?: unknown, code?: unknown, params?: unknown }

function getApiErrorBody(error: unknown): ApiErrorBody | undefined {
  const candidate = error as { data?: ApiErrorBody, response?: { _data?: ApiErrorBody } }
  return candidate?.data ?? candidate?.response?._data
}

/** 后端错误码对应的本地化文案；没有 code 或该 code 尚无翻译时返回 undefined。 */
export function getApiErrorCodeMessage(error: unknown): string | undefined {
  const body = getApiErrorBody(error)
  if (typeof body?.code !== 'string') return undefined
  const key = `apiErrors.${body.code}`
  const params = body.params && typeof body.params === 'object' ? body.params as Record<string, unknown> : undefined
  const message = translate(key, params)
  return message && message !== key ? message : undefined
}

export function getApiErrorDetail(error: unknown, fallback: string): string {
  const coded = getApiErrorCodeMessage(error)
  if (coded) return coded
  const candidate = error as {
    data?: { detail?: unknown }
    response?: { _data?: { detail?: unknown } }
    message?: string
  }
  const detail = candidate?.data?.detail ?? candidate?.response?._data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map(item => typeof item?.msg === 'string' ? item.msg : String(item))
      .join('；')
  }
  return candidate?.message || fallback
}
