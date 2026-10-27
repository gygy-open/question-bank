import { beforeEach, describe, expect, it } from 'vitest'
import enUS from '../../../i18n/locales/en-US.json'
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

describe('422 校验错误', () => {
  const lookup = (key: string): unknown =>
    key.split('.').reduce<any>((node, part) => node?.[part], enUS)

  beforeEach(() => {
    setTranslator((key, params) => {
      const template = lookup(key)
      if (typeof template !== 'string') return key
      return template.replace(/\{(\w+)\}/g, (_, name) => String(params?.[name] ?? ''))
    })
  })

  it('按 type 翻译并带上字段名与约束', () => {
    const error = {
      data: {
        code: 'validation.failed',
        detail: [
          { type: 'missing', loc: ['body', 'name'], msg: 'Field required' },
          { type: 'string_too_short', loc: ['body', 'password'], msg: 'x', ctx: { min_length: 6 } },
        ],
      },
    }
    expect(getApiErrorDetail(error, 'fallback')).toBe(
      '“name” is required; “password” must be at least 6 characters',
    )
  })

  it('api.ts 把 detail 换成字符串后，仍能从 errors 重新翻译', () => {
    const error = {
      data: {
        code: 'validation.failed',
        detail: 'already localized',
        errors: [{ type: 'int_parsing', loc: ['query', 'subject_id'], msg: 'x' }],
      },
    }
    expect(getApiErrorDetail(error, 'fallback')).toBe('“subject_id” must be an integer')
  })

  it('未知 type 回退到通用文案，自定义 value_error 直接展示业务文案', () => {
    const unknown = { data: { code: 'validation.failed', detail: [{ type: 'weird', loc: ['body', 'x'], msg: 'm' }] } }
    expect(getApiErrorDetail(unknown, 'fallback')).toBe('“x” has an invalid value')
    const custom = { data: { code: 'validation.failed', detail: [{ type: 'value_error', loc: ['body'], msg: 'Value error, 题干不能为空' }] } }
    expect(getApiErrorDetail(custom, 'fallback')).toBe('题干不能为空')
  })

  it('错误列表为空时回退到总括文案，重复项只显示一次', () => {
    expect(getApiErrorDetail({ data: { code: 'validation.failed', detail: [] } }, 'fallback'))
      .toBe(lookup('apiErrors.validation.failed'))
    const dup = { data: { code: 'validation.failed', detail: [
      { type: 'missing', loc: ['body', 'a', 0, 'name'], msg: '' },
      { type: 'missing', loc: ['body', 'b', 0, 'name'], msg: '' },
    ] } }
    expect(getApiErrorDetail(dup, 'fallback')).toBe('“name” is required')
  })
})
