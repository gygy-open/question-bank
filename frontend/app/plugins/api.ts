import { toast } from 'vue-sonner'

export default defineNuxtPlugin((nuxtApp) => {
  const api = $fetch.create({
    baseURL: '/api/v1',
    onRequest({ options }) {
      // 每次请求都重新读取 cookie，而不是复用插件初始化时捕获的 ref。
      // 否则首次登录时（尤其手机端全新浏览器无历史 cookie），插件旧 ref
      // 仍为 null，导致带鉴权的请求缺少 Authorization 头而 401。
      const token = nuxtApp.runWithContext(() => useCookie('token').value) as string | null
      if (token) {
        const headers = new Headers(options.headers)
        headers.set('Authorization', `Bearer ${token}`)
        options.headers = headers
      }
    },
    onResponseError({ response }) {
      // 后端尚未完成首次初始化（数据库或首个管理员）：跳转到安装向导
      const detail = response._data?.detail
      if (response.status === 503 && (detail === 'setup_required' || detail === 'admin_required')) {
        nuxtApp.runWithContext(() => navigateTo('/setup'))
        return
      }
      if (response.status === 401) {
        nuxtApp.runWithContext(() => {
          useCookie('token').value = null
          return navigateTo('/login')
        })
      }
      if (response.status === 403) {
        toast.error('您没有权限执行此操作')
      }
    }
  })

  return {
    provide: {
      api
    }
  }
})
