import { shallowRef } from 'vue'
import type { Locale } from 'date-fns'
import { enUS, zhCN } from 'date-fns/locale'

export const SUPPORTED_LOCALES = ['zh-CN', 'en-US'] as const
export type AppLocale = (typeof SUPPORTED_LOCALES)[number]
export const DEFAULT_LOCALE: AppLocale = 'zh-CN'
export const LOCALE_COOKIE_KEY = 'qb_locale'

const DATE_FNS_LOCALES: Record<AppLocale, Locale> = {
  'zh-CN': zhCN,
  'en-US': enUS,
}

export function isSupportedLocale(value: unknown): value is AppLocale {
  return typeof value === 'string' && (SUPPORTED_LOCALES as readonly string[]).includes(value)
}

/** 按浏览器语言偏好顺序，选出第一个受支持的语言（只比较主语言子标签，如 en-GB → en-US）。 */
export function detectBrowserLocale(languages: readonly string[] | undefined | null): AppLocale | null {
  for (const lang of languages ?? []) {
    const primary = lang.split('-')[0]?.toLowerCase()
    const match = SUPPORTED_LOCALES.find((l) => l.split('-')[0]!.toLowerCase() === primary)
    if (match) return match
  }
  return null
}

/**
 * 当前界面语言的响应式镜像，供 lib/ 下的纯函数使用（它们拿不到 useI18n）。
 * 在渲染期间读取会被追踪，因此切换语言后模板里的格式化结果会自动刷新。
 * 由 app/plugins/i18n.ts 负责与 vue-i18n 保持同步。
 */
export const currentLocale = shallowRef<AppLocale>(DEFAULT_LOCALE)

export function setCurrentLocale(value: string): void {
  currentLocale.value = isSupportedLocale(value) ? value : DEFAULT_LOCALE
}

type Translator = (key: string, params?: Record<string, unknown>, locale?: AppLocale) => string
let translator: Translator | null = null

export function setTranslator(fn: Translator): void {
  translator = fn
}

/**
 * 供 lib/ 与 composables 中拿不到 useI18n 的代码使用（如 await 之后、模块级工具函数）。
 * 组件内请优先使用 useI18n().t。传 locale 时按该语言翻译，而不是当前界面语言。
 */
export function translate(key: string, params?: Record<string, unknown>, locale?: AppLocale): string {
  return translator ? translator(key, params, locale) : key
}

export function getDateFnsLocale(): Locale {
  return DATE_FNS_LOCALES[currentLocale.value]
}

type DateInput = Date | string | number

function toDate(value: DateInput): Date {
  return value instanceof Date ? value : new Date(value)
}

export function formatDateTime(value: DateInput, options?: Intl.DateTimeFormatOptions): string {
  const d = toDate(value)
  if (Number.isNaN(d.getTime())) return String(value)
  return d.toLocaleString(currentLocale.value, options)
}

export function formatDate(value: DateInput, options?: Intl.DateTimeFormatOptions): string {
  const d = toDate(value)
  if (Number.isNaN(d.getTime())) return String(value)
  return d.toLocaleDateString(currentLocale.value, options)
}

export function formatNumber(value: number, options?: Intl.NumberFormatOptions): string {
  return value.toLocaleString(currentLocale.value, options)
}
