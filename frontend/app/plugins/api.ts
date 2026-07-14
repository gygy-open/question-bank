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
