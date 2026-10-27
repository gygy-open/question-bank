import tailwindcss from '@tailwindcss/vite'

const appName = 'QuestionBank'
// 静态兜底标题，只在 JS 加载完成前显示（打包时写死，无法翻译）；之后由 app.vue 按界面语言覆盖。
const appSlogan = 'AI-Native Question Bank'

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

  typescript: {
    tsConfig: {
      compilerOptions: {
        // i18n 测试直接引用 scripts/*.mts，仅用于 vue-tsc 类型检查（noEmit）。
        allowImportingTsExtensions: true,
      },
    },
  },

  // 语言文件位于 <rootDir>/i18n/locales；运行时状态同步见 app/plugins/i18n.ts。
  i18n: {
    strategy: 'no_prefix',
    defaultLocale: 'zh-CN',
    langDir: 'locales',
    locales: [
      { code: 'zh-CN', language: 'zh-CN', name: '简体中文', file: 'zh-CN.json' },
      { code: 'en-US', language: 'en-US', name: 'English', file: 'en-US.json' },
    ],
    // 不用模块自带的检测，避免和 qb_locale cookie 形成两套机制；
    // 首次访问按浏览器语言选择、手动切换后的持久化都在 app/plugins/i18n.ts。
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