export default defineNuxtPlugin(async () => {
  const { fetchUser, user, token } = useAuth()

  if (token.value && !user.value) {
    await fetchUser()
  }
})
