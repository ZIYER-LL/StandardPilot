import { backendMeta } from './backends'

export async function streamAdaptiveChat(settings, message, handlers = {}, signal) {
  const response = await fetch(`${backendMeta(settings).baseUrl}/chat/adaptive/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/x-ndjson' },
    body: JSON.stringify({
      message,
      user_id: settings.userId || 'anonymous',
      conv_id: settings.conversationId || undefined
    }),
    signal
  })
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}: ${await response.text()}`)
  if (!response.body) throw new Error('浏览器未提供流式响应体')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let doneEvent = null
  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (!line.trim()) continue
      const event = JSON.parse(line)
      handlers.onEvent?.(event)
      if (event.type === 'done') doneEvent = event
      if (event.type === 'error') throw new Error(event.message || '自适应请求失败')
    }
    if (done) break
  }
  if (buffer.trim()) handlers.onEvent?.(JSON.parse(buffer))
  return doneEvent
}
