export default defineNuxtRouteMiddleware(async (to) => {
  const { token } = useAuth()

  // 首次安装向导：无需登录即可访问
  if (to.path === '/setup') {
    return
  }

  // 如果用户未登录且访问非登录页，重定向到登录页
  if (!token.value && to.path !== '/login') {
    return navigateTo('/login')
  }

  // 已登录：确保科目上下文就绪，无科目时引导创建第一个科目
  if (token.value) {
    const { init, hasSubjects } = useSubjectContext()
    await init()

    // 已登录访问登录页 -> 回首页（下面的科目校验会接管无科目场景）
    if (to.path === '/login') {
      return navigateTo(hasSubjects.value ? '/' : '/onboarding')
    }

    if (!hasSubjects.value && to.path !== '/onboarding') {
      return navigateTo('/onboarding')
    }
    if (hasSubjects.value && to.path === '/onboarding') {
      return navigateTo('/')
    }
  }
})
