import type { TokenResponse } from '@bisheng/types'

const key = 'bisheng.gateway.access-token'

export const tokenStore = {
  get: () => sessionStorage.getItem(key),
  set: (value: TokenResponse) => sessionStorage.setItem(key, value.access_token),
  clear: () => sessionStorage.removeItem(key),
}

export const authorizationHeader = () => {
  const token = tokenStore.get()
  return token ? { Authorization: `Bearer ${token}` } : {}
}