import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { apiUrl } from '../utils/api'

export interface AuthUser {
  userId: string
  username: string
  displayName: string | null
  avatarUrl?: string | null
  role: string
}

interface LocalProfileOverride {
  displayName?: string | null
  avatarUrl?: string | null
}

const PROFILE_OVERRIDES_KEY = 'soulmeet.auth.profileOverrides.v1'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('auth_token'))
  const user = ref<AuthUser | null>(null)

  const isLoggedIn = computed(() => !!token.value && !!user.value)

  /** 通用请求头（带 JWT） */
  function authHeaders(): Record<string, string> {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token.value) {
      headers['Authorization'] = `Bearer ${token.value}`
    }
    return headers
  }

  function readProfileOverrides(): Record<string, LocalProfileOverride> {
    try {
      const raw = localStorage.getItem(PROFILE_OVERRIDES_KEY)
      if (!raw) return {}
      const parsed = JSON.parse(raw)
      return parsed && typeof parsed === 'object' ? parsed as Record<string, LocalProfileOverride> : {}
    }
    catch {
      return {}
    }
  }

  function writeProfileOverrides(overrides: Record<string, LocalProfileOverride>) {
    try {
      localStorage.setItem(PROFILE_OVERRIDES_KEY, JSON.stringify(overrides))
    }
    catch {
      // Local profile edits should still update the current session if storage is full.
    }
  }

  function applyLocalProfileOverrides(nextUser: AuthUser): AuthUser {
    const override = readProfileOverrides()[nextUser.userId]
    if (!override) return nextUser
    return {
      ...nextUser,
      displayName: Object.prototype.hasOwnProperty.call(override, 'displayName')
        ? override.displayName ?? null
        : nextUser.displayName,
      avatarUrl: Object.prototype.hasOwnProperty.call(override, 'avatarUrl')
        ? override.avatarUrl ?? null
        : nextUser.avatarUrl,
    }
  }

  /** 登录 */
  async function login(username: string, password: string): Promise<void> {
    const resp = await fetch(apiUrl('/api/auth/login'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ method: 'password', username, password }),
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: 'Login failed' }))
      throw new Error(err.detail || 'Login failed')
    }
    const data = await resp.json()
    setSessionFromLogin(data)
  }

  /** API Key 登录 */
  async function loginWithApiKey(apiKey: string): Promise<void> {
    const resp = await fetch(apiUrl('/api/auth/login'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ method: 'api_key', api_key: apiKey }),
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: 'Login failed' }))
      throw new Error(err.detail || 'Login failed')
    }
    const data = await resp.json()
    setSessionFromLogin(data)
  }

  function setSessionFromLogin(data: any) {
    token.value = data.access_token
    localStorage.setItem('auth_token', data.access_token)
    user.value = applyLocalProfileOverrides({
      userId: String(data.user_id),
      username: data.username,
      displayName: data.display_name ?? null,
      avatarUrl: data.avatar_url ?? null,
      role: data.role,
    })
  }

  /** 注册 */
  async function register(
    username: string,
    password: string,
    displayName?: string,
  ): Promise<{ apiKey: string }> {
    const resp = await fetch(apiUrl('/api/auth/register'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password, display_name: displayName || null }),
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ detail: 'Registration failed' }))
      throw new Error(err.detail || 'Registration failed')
    }
    const data = await resp.json()
    return { apiKey: data.api_key }
  }

  /** 获取当前用户信息（用于页面刷新后恢复登录态） */
  async function fetchMe(): Promise<void> {
    if (!token.value) return
    try {
      const resp = await fetch(apiUrl('/api/auth/me'), { headers: authHeaders() })
      if (!resp.ok) {
        logout()
        return
      }
      const data = await resp.json()
      user.value = applyLocalProfileOverrides({
        userId: String(data.user_id),
        username: data.username,
        displayName: data.display_name,
        avatarUrl: data.avatar_url ?? null,
        role: data.role,
      })
    }
    catch {
      logout()
    }
  }

  function updateLocalProfile(payload: { displayName?: string | null; avatarUrl?: string | null }) {
    if (!user.value) return
    const userId = user.value.userId
    const overrides = readProfileOverrides()
    const nextOverride: LocalProfileOverride = { ...(overrides[userId] ?? {}) }
    const nextUser: AuthUser = { ...user.value }

    if (Object.prototype.hasOwnProperty.call(payload, 'displayName')) {
      const normalized = payload.displayName?.trim() || null
      nextOverride.displayName = normalized
      nextUser.displayName = normalized
    }

    if (Object.prototype.hasOwnProperty.call(payload, 'avatarUrl')) {
      const normalized = payload.avatarUrl || null
      nextOverride.avatarUrl = normalized
      nextUser.avatarUrl = normalized
    }

    overrides[userId] = nextOverride
    writeProfileOverrides(overrides)
    user.value = nextUser
  }

  /** 登出 */
  function logout() {
    token.value = null
    user.value = null
    localStorage.removeItem('auth_token')
  }

  return {
    token,
    user,
    isLoggedIn,
    login,
    loginWithApiKey,
    register,
    fetchMe,
    updateLocalProfile,
    logout,
  }
})
