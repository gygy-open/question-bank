import type { Composer } from 'vue-i18n'
import { z } from 'zod'
import { createZodErrorMap } from '@/lib/zodErrorMap'
import { LOCALE_COOKIE_KEY, detectBrowserLocale, isSupportedLocale, setCurrentLocale, setTranslator } from '@/lib/locale'

export default defineNuxtPlugin({
  name: 'app-i18n',
  dependsOn: ['i18n:plugin'],
  async setup(nuxtApp) {
    const i18n = nuxtApp.$i18n as Composer
    const localeCookie = useCookie<string | null>(LOCALE_COOKIE_KEY, {
      maxAge: 60 * 60 * 24 * 365,
      sameSite: 'lax',
    })

    // cookie 只要存在就代表用户做过选择（包括选中文），不再按浏览器语言覆盖。
    const saved = localeCookie.value
    const initial = isSupportedLocale(saved)
      ? saved
      : import.meta.client
        ? detectBrowserLocale(navigator.languages ?? [navigator.language])
        : null
    if (initial && initial !== i18n.locale.value) {
      await i18n.setLocale(initial)
    }
    if (!isSupportedLocale(saved) && initial) {
      localeCookie.value = initial
    }
    setCurrentLocale(i18n.locale.value)

    nuxtApp.hook('i18n:localeSwitched', ({ newLocale }) => {
      setCurrentLocale(newLocale)
      localeCookie.value = newLocale
      // 桌面版托盘菜单跟随用户的显式选择；后端只接受本机请求，网页版/局域网访问时是空操作。
      $fetch('/api/v1/system/desktop-locale', { method: 'PUT', body: { locale: newLocale } }).catch(() => {})
    })

    z.setErrorMap(createZodErrorMap((key, params) => i18n.t(key, params ?? {})))
    setTranslator((key, params, locale) => (locale ? i18n.t(key, params ?? {}, { locale }) : i18n.t(key, params ?? {})))
  },
})
