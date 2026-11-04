import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { wsService } from '@/services/websocket'

// Global State
const username = ref<string | null>(localStorage.getItem('auth_username'))
const isLoggedIn = ref(localStorage.getItem('auth_logged_in') === 'true')
// 本机免登录：后端在回环地址 + 非严格模式下直接放行，无需密码。
const isLocalAuto = ref(false)

export function useAuth() {
  const router = useRouter()

  const isAuthenticated = computed(() => isLoggedIn.value)

  function setAuthenticated(user: string, auto = false) {
    username.value = user
    isLoggedIn.value = true
    isLocalAuto.value = auto

    localStorage.setItem('auth_username', user)
    localStorage.setItem('auth_logged_in', 'true')

    // 启动 WebSocket 连接
    wsService.start()
  }

  function clearAuthenticated() {
    username.value = null
    isLoggedIn.value = false
    isLocalAuto.value = false
    localStorage.removeItem('auth_username')
    localStorage.removeItem('auth_logged_in')

    // 停止 WebSocket 连接
    wsService.stop()
  }

  async function logout() {
    // 本机免登录模式没有可撤销的会话，退出登录没有意义，交给 UI 隐藏入口。
    if (isLocalAuto.value) {
      return
    }

    // 撤销后端会话，退出后旧 cookie 也无法继续访问接口。
    clearAuthenticated()
    try {
      await fetch('/auth/logout', { method: 'POST', keepalive: true })
    } catch {
      // 服务不可用时仍清除本地状态。
    }

    // Redirect to login if using router
    if (router) {
      router.push('/login')
    } else {
      window.location.href = '/login'
    }
  }

  async function refreshSession(): Promise<boolean> {
    const savedUsername = localStorage.getItem('auth_username')

    try {
      const response = await fetch('/auth/session', { cache: 'no-store' })
      if (response.ok) {
        const contentType = response.headers.get('content-type') ?? ''
        if (contentType.includes('application/json')) {
          const session = await response.json()
          setAuthenticated(session.username || 'admin', Boolean(session.auto))
          return true
        }

        // 兼容旧版后端：/auth/session 可能被静态页面兜底返回。
        // 旧版接口本身未启用 Cookie 鉴权，保留已验证的本地登录状态。
        if (!savedUsername) {
          clearAuthenticated()
          return false
        }
        setAuthenticated(savedUsername)
        return true
      }
    } catch {
      // 服务不可用时不把本地标记当作有效登录。
    }
    clearAuthenticated()
    return false
  }

  async function login(user: string, pass: string): Promise<boolean> {
    try {
      const response = await fetch('/auth/status', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ username: user, password: pass }),
      })

      if (response.ok) {
        setAuthenticated(user)
        return true
      } else {
        return false
      }
    } catch (e) {
      console.error('Login error', e)
      return false
    }
  }

  return {
    username,
    isAuthenticated,
    isLocalAuto,
    login,
    logout,
    refreshSession,
  }
}
