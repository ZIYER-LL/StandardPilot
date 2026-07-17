const DEFAULT_ENDPOINT = import.meta.env.VITE_API_URL || import.meta.env.VITE_PYTHON_API_URL || '/api/python'

export function createInitialSettings() {
  const saved = readSettings()
  return {
    endpoint: saved.endpoint || saved.endpoints?.python || DEFAULT_ENDPOINT,
    userId: saved.userId || 'researcher-001',
    conversationId: saved.conversationId || ''
  }
}

export function saveSettings(settings) {
  localStorage.setItem('standardpilot.frontend.settings', JSON.stringify(settings))
}

export function backendMeta(settings) {
  return {
    id: 'standardpilot',
    label: 'StandardPilot Python',
    baseUrl: normalizeBaseUrl(settings.endpoint || DEFAULT_ENDPOINT)
  }
}

export async function requestHealth(settings) {
  return requestJson(backendMeta(settings).baseUrl, '/health')
}

export async function requestMonitor(settings) {
  return requestJson(backendMeta(settings).baseUrl, '/monitor')
}

export async function requestKnowledgeStats(settings) {
  return requestJson(backendMeta(settings).baseUrl, '/knowledge/stats')
}

export async function requestSearch(settings, query, topK = 5) {
  const params = new URLSearchParams({ query, top_k: String(topK) })
  return requestJson(backendMeta(settings).baseUrl, `/search?${params}`, { method: 'POST' })
}

export async function requestChat(settings, message) {
  const raw = await requestJson(backendMeta(settings).baseUrl, '/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      user_id: settings.userId || 'anonymous',
      conv_id: settings.conversationId || undefined
    })
  })
  return normalizeChatResponse(raw)
}

export async function streamChat(settings, message, handlers = {}, signal) {
  const baseUrl = backendMeta(settings).baseUrl
  const response = await fetch(`${baseUrl}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/x-ndjson' },
    body: JSON.stringify({
      message,
      user_id: settings.userId || 'anonymous',
      conv_id: settings.conversationId || undefined
    }),
    signal
  })
  if (!response.ok) {
    const detail = await response.text()
    throw new Error(`${response.status} ${response.statusText}: ${detail}`)
  }
  if (!response.body) throw new Error('浏览器未提供流式响应体')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let doneEvent = null

  const dispatch = (event) => {
    handlers.onEvent?.(event)
    const key = `on${event.type.split('_').map((part) => part[0].toUpperCase() + part.slice(1)).join('')}`
    handlers[key]?.(event)
    if (event.type === 'done') doneEvent = event
    if (event.type === 'error') throw new Error(event.message || '流式请求失败')
  }

  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      const text = line.trim()
      if (!text) continue
      dispatch(JSON.parse(text))
    }
    if (done) break
  }
  if (buffer.trim()) dispatch(JSON.parse(buffer.trim()))
  return doneEvent
}

export async function listConversations(settings, limit = 50) {
  const params = new URLSearchParams({ user_id: settings.userId || 'anonymous', limit: String(limit) })
  return requestJson(backendMeta(settings).baseUrl, `/conversations?${params}`)
}

export async function getConversation(settings, conversationId) {
  const params = new URLSearchParams({ user_id: settings.userId || 'anonymous' })
  return requestJson(backendMeta(settings).baseUrl, `/conversations/${encodeURIComponent(conversationId)}?${params}`)
}

export async function deleteConversation(settings, conversationId) {
  const params = new URLSearchParams({ user_id: settings.userId || 'anonymous' })
  return requestJson(backendMeta(settings).baseUrl, `/conversations/${encodeURIComponent(conversationId)}?${params}`, { method: 'DELETE' })
}

export async function listTraces(settings, { limit = 50, conversationId = '' } = {}) {
  const params = new URLSearchParams({ limit: String(limit), user_id: settings.userId || 'anonymous' })
  if (conversationId) params.set('conv_id', conversationId)
  return requestJson(backendMeta(settings).baseUrl, `/traces?${params}`)
}

export async function getTrace(settings, traceId) {
  return requestJson(backendMeta(settings).baseUrl, `/traces/${encodeURIComponent(traceId)}`)
}

export async function requestObservabilitySummary(settings, limit = 100) {
  const params = new URLSearchParams({ limit: String(limit) })
  return requestJson(backendMeta(settings).baseUrl, `/observability/summary?${params}`)
}

export async function addKnowledge(settings, documents) {
  return requestJson(backendMeta(settings).baseUrl, '/knowledge/add', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ documents })
  })
}

export async function uploadKnowledge(settings, file) {
  const form = new FormData()
  form.append('file', file)
  return requestJson(backendMeta(settings).baseUrl, '/knowledge/upload', {
    method: 'POST',
    body: form
  })
}

function normalizeChatResponse(raw) {
  return {
    conversationId: raw.conv_id || raw.conversation_id || raw.conversationId || '',
    response: raw.response || '',
    intent: raw.intent || 'other',
    agentType: raw.agent_type || raw.agentType || '',
    escalated: Boolean(raw.escalated),
    latencyMs: Number(raw.latency_ms ?? raw.latencyMs ?? 0),
    knowledgeUsed: Boolean(raw.knowledge_used ?? raw.knowledgeUsed),
    raw
  }
}

async function requestJson(baseUrl, path, options = {}) {
  const url = `${normalizeBaseUrl(baseUrl)}${path}`
  const response = await fetch(url, options)
  const text = await response.text()
  let data = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = text
  }
  if (!response.ok) {
    const detail = typeof data === 'string' ? data : JSON.stringify(data)
    throw new Error(`${response.status} ${response.statusText}: ${detail}`)
  }
  return data
}

function normalizeBaseUrl(value) {
  const raw = String(value || '').trim().replace(/\/+$/, '')
  if (!raw) return ''
  if (raw.startsWith('/')) return raw
  if (/^https?:\/\//i.test(raw)) return raw
  return `http://${raw}`
}

function readSettings() {
  try {
    return JSON.parse(localStorage.getItem('standardpilot.frontend.settings') || localStorage.getItem('echomind.frontend.settings') || '{}')
  } catch {
    return {}
  }
}
