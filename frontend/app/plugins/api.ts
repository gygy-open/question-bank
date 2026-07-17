export default defineNuxtPlugin((nuxtApp) => {
  const token = useCookie('token')

  const api = $fetch.create({
    baseURL: '/api/v1',
    onRequest({ request, options }) {
      if (token.value) {
        const headers = new Headers(options.headers)
        headers.set('Authorization', `Bearer ${token.value}`)
        options.headers = headers
      }
    },
    onResponseError({ response }) {
      // 后端尚未完成首次安装：跳转到安装向导
      if (response.status === 503 && response._data?.detail === 'setup_required') {
        navigateTo('/setup')
        return
      }
      if (response.status === 401) {
        token.value = null
        navigateTo('/login')
      }
    }
  })

  return {
    provide: {
      api
    }
  }
})
