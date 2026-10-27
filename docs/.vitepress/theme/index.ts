import type { Theme } from 'vitepress'
import DefaultTheme from 'vitepress/theme'
import { LANG_STORAGE_KEY, bilingualLocale, redirectToEnglishIfPreferred } from '../lang-redirect.mts'

function rememberLocale(pathname: string, base: string) {
  const locale = bilingualLocale(pathname, base)
  if (!locale) return
  try {
    localStorage.setItem(LANG_STORAGE_KEY, locale)
  } catch {}
}

export default {
  extends: DefaultTheme,
  enhanceApp({ router, siteData }) {
    if (typeof window === 'undefined') return
    const base = siteData.value.base
    // Decide before remembering, otherwise the Chinese page would be stored as the preference.
    if (redirectToEnglishIfPreferred(base)) return
    rememberLocale(window.location.pathname, base)
    const prev = router.onAfterRouteChange
    router.onAfterRouteChange = (to) => {
      prev?.(to)
      rememberLocale(new URL(to, window.location.href).pathname, base)
    }
  }
} satisfies Theme
