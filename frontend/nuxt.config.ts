import tailwindcss from '@tailwindcss/vite'

const appName = 'QuestionBank'
const appSlogan = 'AI原生的题库系统'

// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',

  devtools: { enabled: false },

  ssr: false,

  runtimeConfig: {
    public: {
      appName,
    }
  },

  app: {
    // 页面默认缓存；单页可用 definePageMeta({ keepalive: false }) 退出。
    keepalive: true,
    head: {
      title: `${appName} - ${appSlogan}`, // default fallback title
      htmlAttrs: {
        lang: 'zh-CN',
      },
      link: [
        { rel: 'icon', type: 'image/svg+xml', href: '/logo.svg' },
      ],
    },
  },

  css: [
    '~/assets/css/tailwind.css',
    'katex/dist/katex.min.css',
    'vue-sonner/style.css'
  ],

  vue: {
    compilerOptions: {
      isCustomElement: (tag) => tag === 'math-field'
    }
  },

  vite: {
    plugins: [
      tailwindcss(),
    ],
  },

  modules: ['shadcn-nuxt', '@nuxtjs/i18n'],

  // 语言文件位于 <rootDir>/i18n/locales；运行时状态同步见 app/plugins/i18n.ts。
  i18n: {
    strategy: 'no_prefix',
    defaultLocale: 'zh-CN',
    langDir: 'locales',
    locales: [
      { code: 'zh-CN', language: 'zh-CN', name: '简体中文', file: 'zh-CN.json' },
      { code: 'en-US', language: 'en-US', name: 'English', file: 'en-US.json' },
    ],
    // 翻译未覆盖全站前不按浏览器语言自动切换，避免英文环境下出现中英混杂；
    // 用户手动选择的语言由 app/plugins/i18n.ts 写入 cookie 持久化。
    detectBrowserLanguage: false,
    vueI18n: './i18n.config.ts',
  },

  shadcn: {
    /**
     * Prefix for all the imported component.
     * @default "Ui"
     */
    prefix: '',
    /**
     * Directory that the component lives in.
     * Will respect the Nuxt aliases.
     * @link https://nuxt.com/docs/api/nuxt-config#alias
     * @default "@/components/ui"
     */
    componentDir: '@/components/ui'
  },

  nitro: {
    devProxy: {
      '/api': { 
        target: (process.env.API_BASE_URL || 'http://localhost:8000') + '/api',
        changeOrigin: true
      },
      '/static': { 
        target: (process.env.API_BASE_URL || 'http://localhost:8000') + '/static',
        changeOrigin: true
      },
      '/uploads': { 
        target: (process.env.API_BASE_URL || 'http://localhost:8000') + '/uploads',
        changeOrigin: true
      },
    }
  },

})