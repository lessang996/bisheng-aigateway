const env = (import.meta as unknown as { env: Record<string, string | undefined> }).env

const value = (name: string, fallback: string) => env[name] || fallback

export const appConfig = {
  apiBaseUrl: value('VITE_API_BASE_URL', '/api'),
  appName: value('VITE_APP_NAME', 'AI Gateway'),
  enableMock: value('VITE_ENABLE_MOCK', 'false') === 'true',
}