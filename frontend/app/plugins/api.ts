import type { Composer } from 'vue-i18n'
import { toast } from 'vue-sonner'
import { getApiErrorCodeMessage } from '@/lib/apiErrors'

export default defineNuxtPlugin((nuxtApp) => {
  // 在回调里再读取，避免插件初始化顺序影响 $i18n 是否已就绪。
  const i18n = () => nuxtApp.$i18n as Composer
  const api = $fetch.create({
    baseURL: '/api/v1',
    onRequest({ options }) {
      const headers = new Headers(options.headers)
      // 供后端按界面语言返回本地化内容（错误信息等），后端未处理时无副作用。
      headers.set('Accept-Language', i18n().locale.value)
      // 每次请求都重新读取 cookie，而不是复用插件初始化时捕获的 ref。
      // 否则首次登录时（尤其手机端全新浏览器无历史 cookie），插件旧 ref
      // 仍为 null，导致带鉴权的请求缺少 Authorization 头而 401。
      const token = nuxtApp.runWithContext(() => useCookie('token').value) as string | null
      if (token) {
        headers.set('Authorization', `Bearer ${token}`)
      }
      options.headers = headers
    },
    onResponseError({ response }) {
      // 后端尚未完成首次初始化（数据库或首个管理员）：跳转到安装向导
      const detail = response._data?.detail
      if (response.status === 503 && (detail === 'setup_required' || detail === 'admin_required')) {
        nuxtApp.runWithContext(() => navigateTo('/setup'))
        return
      }
      // 带错误码的响应：把 detail 换成本地化文案，这样各处直接读取 e.data.detail 的代码也能显示当前语言。
      const localized = getApiErrorCodeMessage({ data: response._data })
      if (localized && response._data) {
        // 422 的 detail 原本是错误列表；换成字符串前先留一份，供 getApiErrorCodeMessage 再次翻译。
        if (Array.isArray(response._data.detail)) response._data.errors = response._data.detail
        response._data.detail = localized
      }
      if (response.status === 401) {
        nuxtApp.runWithContext(() => {
          useCookie('token').value = null
          return navigateTo('/login')
        })
      }
      if (response.status === 403) {
        toast.error(i18n().t('errors.forbidden'))
      }
    }
  })

  return {
    provide: {
      api
    }
  }
})
