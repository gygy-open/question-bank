// Browser-language detection for the docs site. GitHub Pages is static, so the
// redirect runs client-side: first-time visitors whose preferred browser
// language is not Chinese are sent to the English page, and the theme remembers
// the locale of every bilingual page visited afterwards, so a manual switch via
// the language menu sticks.
//
// The check runs twice: as an inline <head> script in production builds (before
// first paint), and from the theme on startup, because the dev server injects
// config `head` tags only after the app has mounted.

export const LANG_STORAGE_KEY = 'qb-docs-locale'

// Sections that exist in both languages; keep in sync with SCOPE in scripts/i18n-docs.mjs.
const BILINGUAL = '^(en/)?(|index(\\.html)?|(guide|desktop|server|admin|features|development)/.*)$'

/** 'en' | 'zh' for pages available in both languages, otherwise null. */
export function bilingualLocale(pathname: string, base: string): 'en' | 'zh' | null {
  if (!pathname.startsWith(base)) return null
  const m = new RegExp(BILINGUAL).exec(pathname.slice(base.length))
  if (!m) return null
  return m[1] ? 'en' : 'zh'
}

// Self-contained (serialized into the inline head script): returns the English
// URL to redirect to, or null.
function englishRedirect(base: string, pattern: string, key: string): string | null {
  try {
    const p = location.pathname
    if (p.indexOf(base) !== 0) return null
    const rest = p.slice(base.length)
    const m = new RegExp(pattern).exec(rest)
    if (!m || m[1]) return null
    let pref = localStorage.getItem(key)
    if (!pref) {
      if (/bot|crawl|spider|slurp/i.test(navigator.userAgent)) return null
      const lang = (navigator.languages && navigator.languages[0]) || navigator.language || ''
      pref = /^zh\b/i.test(lang) ? 'zh' : 'en'
    }
    return pref === 'en' ? base + 'en/' + rest + location.search : null
  } catch {
    return null
  }
}

export function redirectToEnglishIfPreferred(base: string): boolean {
  const target = englishRedirect(base, BILINGUAL, LANG_STORAGE_KEY)
  if (target) location.replace(target)
  return !!target
}

export function redirectScript(base: string): string {
  const args = [base, BILINGUAL, LANG_STORAGE_KEY].map((a) => JSON.stringify(a)).join(',')
  return `(function(){var t=(${englishRedirect.toString()})(${args});if(t)location.replace(t)})()`
}
