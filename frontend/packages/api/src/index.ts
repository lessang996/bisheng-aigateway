import { authorizationHeader, tokenStore } from '@bisheng/auth'
import { appConfig } from '@bisheng/config'
import type { TokenResponse } from '@bisheng/types'

export class ApiClient {
  constructor(private readonly baseUrl = appConfig.apiBaseUrl) {}

  async json<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers)
    headers.set('Accept', 'application/json')
    headers.set('Content-Type', 'application/json')
    Object.entries(authorizationHeader()).forEach(([key, value]) => headers.set(key, value))
    const response = await fetch(`${this.baseUrl}${path}`, { ...init, headers })

    if (response.status === 401) {
      tokenStore.clear()
      throw new Error('登录已过期，请重新登录')
    }

    if (!response.ok) {
      const body = await response.json().catch(() => null) as { detail?: unknown; message?: string } | null
      throw new Error(typeof body?.detail === 'string' ? body.detail : body?.message || `请求失败（${response.status}）`)
    }

    return response.json() as Promise<T>
  }

  stream(path: string, init: RequestInit = {}) {
    const headers = new Headers(init.headers)
    headers.set('Accept', 'text/event-stream')
    headers.set('Content-Type', 'application/json')
    Object.entries(authorizationHeader()).forEach(([key, value]) => headers.set(key, value))
    return fetch(`${this.baseUrl}${path}`, { ...init, headers })
  }
}

export const apiClient = new ApiClient()

export const authApi = {
  login: (username: string, password: string) =>
    apiClient.json<TokenResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    }),
}

export const reportApi = {
  create: (userInput: string, token: string, signal: AbortSignal) => {
    const headers: HeadersInit = token.trim() ? { Authorization: `Bearer ${token.trim()}` } : {}
    return apiClient.stream('/chat/report', {
      method: 'POST',
      headers,
      body: JSON.stringify({ userInput }),
      signal,
    })
  },
}

export const systemApi = {
  health: () => apiClient.json<{ status: string }>('/health/live'),
  calls: () =>
    apiClient.json<{ calls: Array<{ endpoint: string; count: number }> }>('/stats/calls'),
}