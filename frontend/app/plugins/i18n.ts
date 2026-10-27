import { z } from 'zod'
import { createZodErrorMap } from '@/lib/zodErrorMap'
import { DEFAULT_LOCALE, LOCALE_COOKIE_KEY, isSupportedLocale, setCurrentLocale, setTranslator } from '@/lib/locale'

export default defineNuxtPlugin({
  name: 'app-i18n',
  dependsOn: ['i18n:plugin'],
  async setup(nuxtApp) {
    const i18n = nuxtApp.$i18n
    const localeCookie = useCookie<string | null>(LOCALE_COOKIE_KEY, {
      maxAge: 60 * 60 * 24 * 365,
      sameSite: 'lax',
    })

    const saved = localeCookie.value
    if (isSupportedLocale(saved) && saved !== i18n.locale.value) {
      await i18n.setLocale(saved)
    }
    setCurrentLocale(i18n.locale.value)

    nuxtApp.hook('i18n:localeSwitched', ({ newLocale }) => {
      setCurrentLocale(newLocale)
      localeCookie.value = newLocale === DEFAULT_LOCALE ? null : newLocale
    })

    z.setErrorMap(createZodErrorMap((key, params) => i18n.t(key, params ?? {})))
    setTranslator((key, params, locale) => (locale ? i18n.t(key, params ?? {}, { locale }) : i18n.t(key, params ?? {})))
  },
})
