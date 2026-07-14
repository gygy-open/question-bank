export default defineNuxtRouteMiddleware((to) => {
  const { token } = useAuth()

  // 如果用户已登录且访问登录页，重定向到首页
  if (token.value && to.path === '/login') {
    return navigateTo('/')
  }

  // 如果用户未登录且访问非登录页，重定向到登录页
  if (!token.value && to.path !== '/login') {
    return navigateTo('/login')
  }
})
