export interface ApiError { code: string; message: string; details?: unknown; request_id?: string; timestamp?: string }
export interface TokenResponse { access_token: string; refresh_token?: string; expires_in: number }
export interface AgentEvent { eventType?: string; data?: { type?: string; text?: string; message?: string; finishReason?: string } }
export interface StreamEvent { event?: string; data: string; id?: string }
export interface DashboardMetric { label: string; value: string; change: string; tone: 'blue' | 'violet' | 'orange' | 'green' }
