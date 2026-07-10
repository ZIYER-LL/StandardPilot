const DEFAULT_BACKEND = {
  id: 'standardpilot',
  label: 'StandardPilot',
  baseUrl: import.meta.env.VITE_STANDARDPILOT_API_URL || '/api/standardpilot',
  port: '8000'
}

const STORAGE_KEY = 'standardpilot.frontend.settings'

export function createInitialSettings() {
  const saved = readSettings()
  return {
    backend: 'standardpilot',
    userId: saved.userId || 'u1001',
    conversationId: saved.conversationId || '',
    endpoint: saved.endpoint || saved.endpoints?.standardpilot || DEFAULT_BACKEND.baseUrl
  }
}

export function saveSettings(settings) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({
    userId: settings.userId,
    conversationId: settings.conversationId,
    endpoint: settings.endpoint || DEFAULT_BACKEND.baseUrl
  }))
}

export function backendMeta(settings) {
  return {
    ...DEFAULT_BACKEND,
    baseUrl: normalizeBaseUrl(settings.endpoint || DEFAULT_BACKEND.baseUrl)
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

export async function requestSkills(settings) {
  return requestJson(backendMeta(settings).baseUrl, '/skills')
}

export async function reloadSkills(settings) {
  return requestJson(backendMeta(settings).baseUrl, '/skills/reload', { method: 'POST' })
}

export async function requestEvalRun(settings) {
  return requestJson(backendMeta(settings).baseUrl, '/eval/run', { method: 'POST' })
}

export async function requestSearch(settings, query, topK = 5) {
  const params = new URLSearchParams({ query, top_k: String(topK) })
  return requestJson(backendMeta(settings).baseUrl, `/search?${params}`, { method: 'POST' })
}

export async function requestChat(settings, message) {
  const meta = backendMeta(settings)
  const payload = buildChatPayload(settings, message)
  const raw = await requestJson(meta.baseUrl, '/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  return normalizeChatResponse(raw)
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

function buildChatPayload(settings, message) {
  return {
    message,
    user_id: settings.userId || 'anonymous',
    conv_id: settings.conversationId || undefined
  }
}

function normalizeChatResponse(raw) {
  return {
    backend: DEFAULT_BACKEND.id,
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
  return String(value || '').replace(/\/+$/, '')
}

function readSettings() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
  } catch {
    return {}
  }
}
