export default defineNuxtRouteMiddleware((to, from) => {
  const { user } = useAuth()
  
  if (!user.value?.is_superuser) {
    return navigateTo('/')
  }
})
