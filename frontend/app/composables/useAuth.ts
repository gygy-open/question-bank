import type { User, LoginRequest, UserUpdatePassword } from '~/types'

export const useAuth = () => {
  const token = useCookie<string | null>('token', {
    maxAge: 60 * 60 * 24 * 7, // 7 days
    path: '/'
  })
  
  const user = useState<User | null>('auth-user', () => null)
  const loading = useState<boolean>('auth-loading', () => false)

  const { $api } = useNuxtApp()

  const fetchUser = async (): Promise<User | null> => {
    if (!token.value) {
      user.value = null
      return null
    }
    
    try {
      loading.value = true
      const data = await $api<User>('/users/me')
      user.value = data
      return data
    } catch (error) {
      console.error('Failed to fetch user', error)
      token.value = null
      user.value = null
      return null
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
      // 校验令牌是否真的可用：拉取当前用户成功才算登录成功。
      // 否则（如手机端时钟偏差、Cookie 未持久化导致 /users/me 失败）
      // fetchUser 会清空 token，此处需抛出真实错误，避免"假成功"。
      const loggedInUser = await fetchUser()
      if (!loggedInUser) {
        token.value = null
        throw new Error('登录校验失败，请检查网络连接与设备时间后重试')
      }
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
