import { translate } from '@/lib/locale'

export function getApiErrorStatus(error: unknown): number | undefined {
  const candidate = error as { statusCode?: number, status?: number, response?: { status?: number } }
  return candidate?.statusCode ?? candidate?.status ?? candidate?.response?.status
}

export function isRevisionConflict(error: unknown): boolean {
  return getApiErrorStatus(error) === 409
}

type ApiErrorBody = { detail?: unknown, code?: unknown, params?: unknown, errors?: unknown }

const VALIDATION_CODE = 'validation.failed'
const LOCATION_PREFIXES = new Set(['body', 'query', 'path', 'header', 'cookie'])
const MAX_VALIDATION_MESSAGES = 3

type ValidationItem = { type?: unknown, loc?: unknown, msg?: unknown, ctx?: unknown }

function validationField(loc: unknown): string {
  if (!Array.isArray(loc)) return ''
  const names = loc.filter((part): part is string => typeof part === 'string' && !LOCATION_PREFIXES.has(part))
  return names.at(-1) ?? ''
}

function validationMessage(item: ValidationItem): string {
  const field = validationField(item.loc)
  const ctx = item.ctx && typeof item.ctx === 'object' ? item.ctx as Record<string, unknown> : {}
  if (typeof item.type === 'string') {
    const key = `apiErrors.validation.types.${item.type}`
    const text = translate(key, { ...ctx, field })
    if (text && text !== key) return text
    // 自定义校验器（value_error）的 msg 是业务文案，直接展示。
    if (item.type === 'value_error' && typeof item.msg === 'string') {
      return item.msg.replace(/^Value error, /, '')
    }
  }
  return field
    ? translate('apiErrors.validation.invalid', { field })
    : translate('apiErrors.validation.invalidNoField')
}

/** 把 422 的 pydantic 错误列表翻译成当前语言；列表为空或格式不对时返回 undefined。 */
export function formatValidationErrors(items: unknown): string | undefined {
  if (!Array.isArray(items) || items.length === 0) return undefined
  const messages = items
    .slice(0, MAX_VALIDATION_MESSAGES)
    .map(item => validationMessage((item ?? {}) as ValidationItem))
  return [...new Set(messages)].join(translate('apiErrors.validation.separator'))
}

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
  if (body.code === VALIDATION_CODE) {
    // api.ts 会把 detail 换成已翻译的字符串，原始列表保留在 errors 里。
    const items = Array.isArray(body.detail) ? body.detail : body.errors
    return formatValidationErrors(items) ?? translate('apiErrors.validation.failed')
  }
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
