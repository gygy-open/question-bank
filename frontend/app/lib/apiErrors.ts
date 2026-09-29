export function getApiErrorStatus(error: unknown): number | undefined {
  const candidate = error as { statusCode?: number, status?: number, response?: { status?: number } }
  return candidate?.statusCode ?? candidate?.status ?? candidate?.response?.status
}

export function isRevisionConflict(error: unknown): boolean {
  return getApiErrorStatus(error) === 409
}

export function getApiErrorDetail(error: unknown, fallback: string): string {
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
