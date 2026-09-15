import type { StreamEvent } from '../types/api'

export async function* parseSse(response: Response): AsyncGenerator<StreamEvent> {
  if (!response.body) throw new Error('服务器未返回可读取的流')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  const emit = (block: string): StreamEvent | null => {
    const event: StreamEvent = { data: '' }
    for (const line of block.split(/\r?\n/)) {
      if (line.startsWith('event:')) event.event = line.slice(6).trim()
      else if (line.startsWith('id:')) event.id = line.slice(3).trim()
      else if (line.startsWith('data:')) event.data += (event.data ? '\n' : '') + line.slice(5).trimStart()
    }
    return event.data || event.event ? event : null
  }
  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
    const blocks = buffer.split(/\r?\n\r?\n/)
    buffer = blocks.pop() || ''
    for (const block of blocks) {
      const event = emit(block)
      if (event) yield event
    }
    if (done) break
  }
  const event = emit(buffer)
  if (event) yield event
}
