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

/**
 * 后端把"本身也需要翻译的片段"（如模型槽位名）以 `<name>_ref` 参数传来，值是 `apiErrors.refs.` 下的键，
 * 多个用逗号分隔。这里先翻译成 `<name>` 再插值，避免后端写死某种语言的名词。
 */
function resolveRefParams(params: Record<string, unknown> | undefined): Record<string, unknown> | undefined {
  if (!params) return params
  const resolved: Record<string, unknown> = {}
  for (const [name, value] of Object.entries(params)) {
    if (name.endsWith('_ref') && typeof value === 'string') {
      const parts = value.split(',').map((ref) => {
        const key = `apiErrors.refs.${ref}`
        const text = translate(key)
        return text && text !== key ? text : ref
      })
      resolved[name.slice(0, -4)] = parts.join(translate('apiErrors.refs.separator'))
    } else {
      resolved[name] = value
    }
  }
  return resolved
}

/** 后端错误码对应的本地化文案；没有 code 或该 code 尚无翻译时返回 undefined。 */
export function getApiErrorCodeMessage(error: unknown): string | undefined {
  const body = getApiErrorBody(error)
  if (typeof body?.code !== 'string') return undefined
  const key = `apiErrors.${body.code}`
  const rawParams = body.params && typeof body.params === 'object' ? body.params as Record<string, unknown> : undefined
  const message = translate(key, resolveRefParams(rawParams))
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
