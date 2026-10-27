import { defineConfig } from 'vitepress'
import { redirectScript } from './lang-redirect.mts'
import { en } from './locales/en.mts'
import { zh, zhSearch } from './locales/zh.mts'

// https://vitepress.dev/reference/site-config
const base = '/question-bank/'

export default defineConfig({
  // Project Pages: https://gygy-open.github.io/question-bank/
  base,

  lastUpdated: true,
  cleanUrls: true,
  metaChunk: true,

  // Internal design specs are not part of the published site.
  srcExclude: ['specs/**', 'design/**'],

  head: [
    ['link', { rel: 'icon', href: `${base}logo.svg` }],
    ['script', {}, redirectScript(base)]
  ],

  // zh-CN is the source language; see scripts/i18n-docs.mjs for the translation workflow.
  locales: {
    root: zh,
    en
  },

  themeConfig: {
    logo: '/logo.svg',

    socialLinks: [
      { icon: 'github', link: 'https://github.com/gygy-open/question-bank' }
    ],

    search: {
      provider: 'local',
      options: { locales: zhSearch }
    }
  }
})
