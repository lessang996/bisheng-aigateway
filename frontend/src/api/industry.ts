import { request } from './request'

export function createIndustryReport(userInput: string, token: string, signal: AbortSignal): Promise<Response> {
  const headers: HeadersInit = { 'Content-Type': 'application/json', Accept: 'text/event-stream' }
  if (token.trim()) headers.Authorization = `Bearer ${token.trim()}`
  return request(`${import.meta.env.VITE_API_BASE_URL || ''}/api/chat/report`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ userInput }),
    signal,
  })
}
