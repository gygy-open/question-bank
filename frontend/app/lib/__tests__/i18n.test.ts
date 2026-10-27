/// <reference types="node" />
import { describe, expect, it } from 'vitest'
import { z } from 'zod'
import { resolve } from 'node:path'
import { check, resolvePaths } from '../../../scripts/i18n-core.mts'
import { checkHardcoded } from '../../../scripts/i18n-hardcoded.mts'
import { createZodErrorMap } from '@/lib/zodErrorMap'
import { currentLocale, detectBrowserLocale, formatDate, setCurrentLocale } from '@/lib/locale'
import { formatRelativeTime } from '@/lib/utils'

describe('locale files', () => {
  // 与 `pnpm i18n:check` 相同：key 集合/顺序、过期译文、占位符、vue-i18n 语法
  it('pass i18n:check', () => {
    const paths = resolvePaths(resolve(process.cwd(), 'i18n'))
    expect(check(paths)).toEqual([])
  })

  it('have no hardcoded Chinese outside the baseline', () => {
    const root = process.cwd()
    expect(checkHardcoded(root, resolve(root, 'i18n/.hardcoded-baseline.json'))).toEqual([])
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

describe('detectBrowserLocale', () => {
  it('picks the first supported language by primary subtag', () => {
    expect(detectBrowserLocale(['en-GB', 'zh-CN'])).toBe('en-US')
    expect(detectBrowserLocale(['fr-FR', 'zh-TW', 'en'])).toBe('zh-CN')
    expect(detectBrowserLocale(['EN'])).toBe('en-US')
  })

  it('returns null when nothing matches', () => {
    expect(detectBrowserLocale(['fr-FR', 'de'])).toBeNull()
    expect(detectBrowserLocale([])).toBeNull()
    expect(detectBrowserLocale(undefined)).toBeNull()
  })
})
