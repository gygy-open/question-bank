import tailwindcss from '@tailwindcss/vite'

const appNmae = 'Question Bank 题库系统'

// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',

  devtools: { enabled: false },

  ssr: false,

  runtimeConfig: {
    public: {
      appName: appNmae,
    }
  },

  app: {
    head: {
      title: appNmae, // default fallback title
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

  modules: ['shadcn-nuxt'],

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