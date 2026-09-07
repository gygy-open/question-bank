export default defineNuxtRouteMiddleware(async (to) => {
  const { token } = useAuth()

  if (to.path === '/test') {
    return
  }

  // 首次安装向导：无需登录即可访问
  if (to.path === '/setup') {
    return
  }

  // 免登录页面：登录与自助注册
  const publicPaths = ['/login', '/register']

  // 如果用户未登录且访问非公开页，重定向到登录页
  if (!token.value && !publicPaths.includes(to.path)) {
    return navigateTo('/login')
  }

  // 已登录：确保学科上下文就绪
  if (token.value) {
    const { user } = useAuth()
    const { init, hasSubjects } = useSubjectContext()
    await init()

    // onboarding(创建第一个学科)是管理员在全新系统上的任务。普通用户即便可见学科为空
    // （未被分配），也不能走 onboarding —— 那是"系统里还没有任何学科"，而非"我没被分配"。
    const isAdmin = !!user.value?.is_superuser
    const needsOnboarding = isAdmin && !hasSubjects.value

    // 已登录访问登录/注册页 -> 回首页（或引导管理员去 onboarding）
    if (publicPaths.includes(to.path)) {
      return navigateTo(needsOnboarding ? '/onboarding' : '/')
    }

    if (needsOnboarding && to.path !== '/onboarding') {
      return navigateTo('/onboarding')
    }
    if (to.path === '/onboarding' && !needsOnboarding) {
      return navigateTo('/')
    }
  }
})
