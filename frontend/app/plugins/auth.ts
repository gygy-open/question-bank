export default defineNuxtPlugin(async () => {
  const route = useRoute()

  if (route.path === '/test') {
    return
  }

  const { fetchUser, user, token } = useAuth()

  if (token.value && !user.value) {
    await fetchUser()
  }
})
