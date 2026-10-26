import { describe, expect, it } from 'vitest'
import { z } from 'zod'
import zhCN from '../../../i18n/locales/zh-CN.json'
import enUS from '../../../i18n/locales/en-US.json'
import { createZodErrorMap } from '@/lib/zodErrorMap'
import { currentLocale, formatDate, setCurrentLocale } from '@/lib/locale'
import { formatRelativeTime } from '@/lib/utils'

type Messages = { [key: string]: string | Messages }

function flattenKeys(obj: Messages, prefix = ''): string[] {
  return Object.entries(obj).flatMap(([k, v]) =>
    typeof v === 'string' ? [`${prefix}${k}`] : flattenKeys(v, `${prefix}${k}.`),
  )
}

function placeholders(obj: Messages): Record<string, string[]> {
  const out: Record<string, string[]> = {}
  const walk = (o: Messages, prefix: string) => {
    for (const [k, v] of Object.entries(o)) {
      if (typeof v === 'string') out[`${prefix}${k}`] = [...v.matchAll(/\{(\w+)\}/g)].map(m => m[1]!).sort()
      else walk(v, `${prefix}${k}.`)
    }
  }
  walk(obj, '')
  return out
}

describe('locale files', () => {
  it('en-US has exactly the same keys as the zh-CN baseline', () => {
    const base = flattenKeys(zhCN as Messages).sort()
    const en = flattenKeys(enUS as Messages).sort()
    expect(en.filter(k => !base.includes(k))).toEqual([])
    expect(base.filter(k => !en.includes(k))).toEqual([])
  })

  it('translations keep the same interpolation placeholders', () => {
    const base = placeholders(zhCN as Messages)
    const en = placeholders(enUS as Messages)
    for (const key of Object.keys(base)) expect(en[key], key).toEqual(base[key])
  })

  it('messages contain no unescaped vue-i18n special characters', () => {
    const get = (o: Messages, path: string) => path.split('.').reduce<any>((acc, p) => acc?.[p], o) as string
    for (const msgs of [zhCN, enUS] as Messages[]) {
      for (const key of flattenKeys(msgs)) {
        const v = get(msgs, key)
        // '@' 与 '|' 在 vue-i18n 中分别表示链接消息和复数分隔，需要写成 {'@'} / {'|'}
        expect(/(^|[^'])[@|]/.test(v), `${key}: ${v}`).toBe(false)
      }
    }
  })
})

describe('createZodErrorMap', () => {
  const t = (key: string, params?: Record<string, unknown>) => `${key}${params ? JSON.stringify(params) : ''}`
  const parse = (schema: z.ZodTypeAny, value: unknown) => {
    const r = schema.safeParse(value, { errorMap: createZodErrorMap(t) })
    return r.success ? null : r.error.issues[0]!.message
  }

  it('maps common issues to translation keys', () => {
    expect(parse(z.string(), undefined)).toBe('validation.required')
    expect(parse(z.string().min(1), '')).toBe('validation.required')
    expect(parse(z.string().min(3), 'a')).toBe('validation.minLength{"min":3}')
    expect(parse(z.string().max(2), 'abc')).toBe('validation.maxLength{"max":2}')
    expect(parse(z.number().min(5), 1)).toBe('validation.min{"min":5}')
    expect(parse(z.array(z.string()).min(1), [])).toBe('validation.minItems{"min":1}')
    expect(parse(z.string().email(), 'x')).toBe('validation.email')
  })

  it('keeps explicit messages', () => {
    expect(parse(z.string().min(1, 'custom'), '')).toBe('custom')
  })
})

describe('locale-aware formatting', () => {
  it('follows the current locale', () => {
    const date = new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString()
    try {
      setCurrentLocale('en-US')
      expect(formatRelativeTime(date)).toMatch(/hours ago/)
      expect(formatDate(new Date(2024, 0, 31))).toBe('1/31/2024')
      setCurrentLocale('zh-CN')
      expect(formatRelativeTime(date)).toMatch(/小时前/)
      expect(formatDate(new Date(2024, 0, 31))).toBe('2024/1/31')
    } finally {
      setCurrentLocale('zh-CN')
    }
  })

  it('falls back to the default locale for unsupported codes', () => {
    setCurrentLocale('fr-FR')
    expect(currentLocale.value).toBe('zh-CN')
  })
})
