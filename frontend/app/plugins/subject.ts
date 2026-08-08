// Runs after auth.ts (alphabetical plugin order) so `user` is already loaded.
export default defineNuxtPlugin(async () => {
  const { token } = useAuth()
  const { init } = useSubjectContext()

  if (token.value) {
    await init()
  }
})
