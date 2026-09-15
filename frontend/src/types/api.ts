export type StreamEvent = {
  event?: string
  data: string
  id?: string
}

export type AgentEvent = {
  eventType?: string
  data?: {
    type?: string
    text?: string
    message?: string
  }
}
