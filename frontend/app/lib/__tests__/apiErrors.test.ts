import { beforeEach, describe, expect, it } from 'vitest'
import { getApiErrorDetail } from '../apiErrors'
import { setTranslator } from '../locale'

describe('getApiErrorDetail', () => {
  beforeEach(() => {
    setTranslator((key, params) => key === 'apiErrors.setup.connection_failed' ? `连接失败：${params?.error}` : key)
  })

  it('优先按错误码翻译并插值', () => {
    const error = { data: { detail: 'Connection failed: x', code: 'setup.connection_failed', params: { error: 'boom' } } }
    expect(getApiErrorDetail(error, 'fallback')).toBe('连接失败：boom')
  })

  it('未登记的错误码回退到 detail', () => {
    const error = { data: { detail: '原文', code: 'unknown.code' } }
    expect(getApiErrorDetail(error, 'fallback')).toBe('原文')
  })

  it('没有 code 时保持原行为', () => {
    expect(getApiErrorDetail({ data: { detail: '原文' } }, 'fallback')).toBe('原文')
  })
})
