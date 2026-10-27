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

  it('把 *_ref 参数先翻译再插值，多个值用分隔符连接', () => {
    const messages: Record<string, string> = {
      'apiErrors.ai_config.in_use_confirm': 'Used as {targets}',
      'apiErrors.refs.model_slot.text': 'text model',
      'apiErrors.refs.model_slot.vision': 'vision model',
      'apiErrors.refs.separator': ', ',
    }
    setTranslator((key, params) => (messages[key] ?? key).replace(/\{(\w+)\}/g, (_, n) => String(params?.[n] ?? '')))
    const error = {
      data: { detail: 'x', code: 'ai_config.in_use_confirm', params: { targets_ref: 'model_slot.text,model_slot.vision' } },
    }
    expect(getApiErrorDetail(error, 'fallback')).toBe('Used as text model, vision model')
  })
})
