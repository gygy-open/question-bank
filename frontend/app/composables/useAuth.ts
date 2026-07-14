import type { User, LoginRequest, UserUpdatePassword } from '~/types'

export const useAuth = () => {
  const token = useCookie<string | null>('token', {
    maxAge: 60 * 60 * 24 * 7, // 7 days
    path: '/'
  })
  
  const user = useState<User | null>('auth-user', () => null)
  const loading = useState<boolean>('auth-loading', () => false)

  const { $api } = useNuxtApp()

  const fetchUser = async () => {
    if (!token.value) {
      user.value = null
      return
    }
    
    try {
      loading.value = true
      const data = await $api<User>('/users/me')
      user.value = data
    } catch (error) {
      console.error('Failed to fetch user', error)
      token.value = null
      user.value = null
    } finally {
      loading.value = false
    }
  }

  const login = async (credentials: LoginRequest) => {
    try {
      loading.value = true
      const formData = new FormData()
      formData.append('username', credentials.username)
      formData.append('password', credentials.password)
      
      const data = await $api<{ access_token: string, token_type: string }>('/login/access-token', {
        method: 'POST',
        body: formData
      })
      
      token.value = data.access_token
      await fetchUser()
      return true
    } catch (error) {
      console.error('Login failed', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  const logout = async () => {
    try {
      if (token.value) {
        await $api('/logout', { method: 'POST' })
      }
    } catch (error) {
      console.error('Logout failed', error)
    } finally {
      token.value = null
      user.value = null
      navigateTo('/login')
    }
  }

  const changePassword = async (data: UserUpdatePassword) => {
    try {
      await $api('/users/me/password', {
        method: 'POST',
        body: data
      })
      return true
    } catch (error) {
      throw error
    }
  }

  return {
    token,
    user,
    loading,
    login,
    logout,
    fetchUser,
    changePassword
  }
}
